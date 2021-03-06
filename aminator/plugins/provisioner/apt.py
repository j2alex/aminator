# -*- coding: utf-8 -*-

#
#
#  Copyright 2013 Netflix, Inc.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
#

"""
aminator.plugins.provisioner.apt
================================
basic apt provisioner
"""
import logging
import os

from aminator.plugins.provisioner.linux import BaseLinuxProvisionerPlugin
from aminator.util.linux import apt_get_install, apt_get_update, deb_package_metadata, command

__all__ = ('AptProvisionerPlugin',)
log = logging.getLogger(__name__)


class AptProvisionerPlugin(BaseLinuxProvisionerPlugin):
    """
    AptProvisionerPlugin takes the majority of its behavior from BaseLinuxProvisionerPlugin
    See BaseLinuxProvisionerPlugin for details
    """
    _name = 'apt'

    def _refresh_package_metadata(self):
        return apt_get_update()

    def _provision_package(self):
        context = self._config.context
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
        if context.package.get('local_install', False):
            return apt_get_localinstall(context.package.arg)
        else:
            return apt_get_install(context.package.arg)

    def _store_package_metadata(self):
        context = self._config.context
        config = self._config.plugins[self.full_name]
        metadata = deb_package_metadata(context.package.arg, config.get('pkg_query_format', ''), context.package.get('local_install', False))
        for x in config.pkg_attributes:
            if x == 'version' and x in metadata:
                if ':' in metadata[x]:
                    # strip epoch element from version
                    vers = metadata[x]
                    metadata[x] = vers[vers.index(':')+1:]
                if '-' in metadata[x]:
                    # debs include release in version so split
                    # version into version-release to compat w/rpm
                    vers, rel = metadata[x].split('-', 1)
                    metadata[x] = vers
                    metadata['release'] = rel
                else:
                    metadata['release'] = 0
                # this is probably not necessary given above
            metadata.setdefault(x, None)
        context.package.attributes = metadata

    def _deactivate_provisioning_service_block(self):
        """
        Prevent packages installing in the chroot from starting
        For debian based distros, we add /usr/sbin/policy-rc.d
        """

        config = self._config.plugins[self.full_name]
        path = self._mountpoint + config.get('policy_file_path', '')
        filename = path + "/" + config.get('policy_file')

        if not os.path.isdir(path):
            log.debug("creating %s", path)
            os.makedirs(path)
            log.debug("created %s", path)

        with open(filename, 'w') as f:
            log.debug("writing %s", filename)
            f.write(config.get('policy_file_content'))
            log.debug("wrote %s", filename)

        os.chmod(filename, config.get('policy_file_mode', ''))

        return True

    def _activate_provisioning_service_block(self):
        """
        Remove policy-rc.d file so that things start when the AMI launches
        """
        config = self._config.plugins[self.full_name]

        policy_file = self._mountpoint + "/" + config.get('policy_file_path', '') + "/" + \
            config.get('policy_file', '')

        if os.path.isfile(policy_file):
            log.debug("removing %s", policy_file)
            os.remove(policy_file)
        else:
            log.debug("The %s was missing, this is unexpected as the "
                      "AptProvisionerPlugin should manage this file", policy_file)

        return True


@command()
def dpkg_install(package):
    return 'dpkg -i {0}'.format(package)


def apt_get_localinstall(package):
    """install deb file with dpkg then resolve dependencies
    """
    dpkg_ret = dpkg_install(package)
    if not dpkg_ret.success:
        log.debug('failure:{0.command} :{0.stderr}'.format(dpkg_ret.result))
        return dpkg_ret

    apt_ret = apt_get_install('--fix-missing')
    if not apt_ret.success:
            log.debug('failure:{0.command} :{0.stderr}'.format(apt_ret.result))
    return apt_ret
