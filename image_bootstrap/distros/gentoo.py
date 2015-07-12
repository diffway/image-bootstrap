# Copyright (C) 2015 Sebastian Pipping <sebastian@pipping.org>
# Licensed under AGPL v3 or later

from __future__ import print_function

import errno
import os
import shutil

from directory_bootstrap.distros.gentoo import GentooBootstrapper
from directory_bootstrap.shared.commands import COMMAND_CHROOT

from image_bootstrap.distros.base import DISTRO_CLASS_FIELD, DistroStrategy
from image_bootstrap.engine import \
        BOOTLOADER__HOST_GRUB2__DRIVE


_ABS_PACKAGE_USE = '/etc/portage/package.use'
_ABS_PACKAGE_KEYWORDS = '/etc/portage/package.keywords'


class GentooStrategy(DistroStrategy):
    DISTRO_KEY = 'gentoo'
    DISTRO_NAME_SHORT = 'Gentoo'
    DISTRO_NAME_LONG = 'Gentoo'

    def __init__(self, messenger, executor, abs_cache_dir,
                mirror_url, max_age_days,
                stage3_date_triple_or_none, repository_date_triple_or_none,
                abs_resolv_conf):
        super(GentooStrategy, self).__init__(
                messenger,
                executor,
                abs_cache_dir,
                abs_resolv_conf,
                )

        self._mirror_url = mirror_url
        self._max_age_days = max_age_days
        self._stage3_date_triple_or_none = stage3_date_triple_or_none
        self._repository_date_triple_or_none = repository_date_triple_or_none

    def select_bootloader(self):
        return BOOTLOADER__HOST_GRUB2__DRIVE

    def allow_autostart_of_services(self, abs_mountpoint, allow):
        pass  # services are not auto-started on Gentoo

    def create_network_configuration(self, abs_mountpoint, use_mtu_tristate):
        pass  # TODO

    def _set_package_use_flags(self, abs_mountpoint, package_name, flags_str, package_atom=None):
        if package_atom is None:
            package_atom = package_name

        filename = os.path.join(abs_mountpoint, _ABS_PACKAGE_USE.lstrip('/'), package_name.replace('/', '--'))
        with open(filename, 'w') as f:
            print('# generated by image-bootstrap', file=f)
            print('%s %s' % (package_name, flags_str), file=f)

    def _set_package_keywords(self, abs_mountpoint, package_name, keywords_str, package_atom=None):
        if package_atom is None:
            package_atom = package_name

        filename = os.path.join(abs_mountpoint,
                _ABS_PACKAGE_KEYWORDS.lstrip('/'),
                package_name.replace('/', '--'),
                )
        with open(filename, 'w') as f:
            print('# generated by image-bootstrap', file=f)
            print('%s %s' % (package_name, keywords_str), file=f)

    def _install_package_atoms(self, abs_mountpoint, env, packages):
        env = env.copy().update({
            'MAKEOPTS': '-j2',
        })
        self._executor.check_call([
                COMMAND_CHROOT,
                abs_mountpoint,
                'emerge',
                '--ignore-default-opts',
                '--tree',
                '--verbose',
                '--jobs', '2',
                ] + list(packages),
                env=env)

    def ensure_chroot_has_grub2_installed(self, abs_mountpoint, env):
        self._set_package_use_flags(abs_mountpoint,
                'sys-boot/grub', 'grub_platforms_pc', 'sys-boot/grub:2')
        self._install_package_atoms(abs_mountpoint, env, ['sys-boot/grub:2'])

    def generate_grub_cfg_from_inside_chroot(self, abs_mountpoint, env):
        cmd = [
                COMMAND_CHROOT,
                abs_mountpoint,
                'grub2-mkconfig',
                '-o', '/boot/grub/grub.cfg',
                ]
        self._executor.check_call(cmd, env=env)

    def generate_initramfs_from_inside_chroot(self, abs_mountpoint, env):
        self._set_package_keywords(abs_mountpoint, 'sys-kernel/dracut', '**')  # TODO ~arch
        self._install_package_atoms(abs_mountpoint, env, ['sys-kernel/dracut'])
        self._executor.check_call([
                COMMAND_CHROOT,
                abs_mountpoint,
                'dracut',
                self.get_initramfs_path(),
                ], env=env)

    def get_chroot_command_grub2_install(self):
        return 'grub2-install'

    def get_cloud_init_datasource_cfg_path(self):
        return '/etc/cloud/cloud.cfg.d/90_datasource.cfg'

    def get_commands_to_check_for(self):
        return [
                COMMAND_CHROOT,
                ]

    def get_initramfs_path(self):
        # NOTE: dracut default is /boot/initramfs-<kernel version>.img
        return '/boot/initramfs.img'

    def get_vmlinuz_path(self):
        return '/boot/vmlinuz'

    def install_cloud_init_and_friends(self, abs_mountpoint, env):
        self._install_package_atoms(abs_mountpoint, env, ['app-emulation/cloud-init'])

    def install_sshd(self, abs_mountpoint, env):
        self._install_package_atoms(abs_mountpoint, env, ['net-misc/openssh'])

    def install_sudo(self, abs_mountpoint, env):
        self._install_package_atoms(abs_mountpoint, env, ['app-admin/sudo'])

    def make_openstack_services_autostart(self, abs_mountpoint, env):
        for service in (
                # TODO network
                'sshd',
                'cloud-init-local',
                'cloud-init',
                'cloud-config',
                'cloud-final',
                ):
            self._executor.check_call([
                COMMAND_CHROOT,
                abs_mountpoint,
                'rc-update',
                'add',
                service,
                ], env=env)

    def perform_in_chroot_shipping_clean_up(self, abs_mountpoint, env):
        pass  # TODO

    def perform_post_chroot_clean_up(self, abs_mountpoint):
        pass  # TODO

    def run_directory_bootstrap(self, abs_mountpoint, architecture, bootloader_approach):
        self._messenger.info('Bootstrapping %s into "%s"...'
                % (self.DISTRO_NAME_SHORT, abs_mountpoint))

        bootstrap = GentooBootstrapper(
                self._messenger,
                self._executor,
                abs_mountpoint,
                self._abs_cache_dir,
                architecture,
                self._mirror_url,
                self._max_age_days,
                self._stage3_date_triple_or_none,
                self._repository_date_triple_or_none,
                self._abs_resolv_conf,
                )
        bootstrap.run()

    def prepare_installation_of_packages(self, abs_mountpoint, env):
        for chroot_abs_path in (
                _ABS_PACKAGE_KEYWORDS,
                _ABS_PACKAGE_USE,
                ):
            try:
                os.makedirs(os.path.join(abs_mountpoint, chroot_abs_path.lstrip('/')), 0755)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

        self._executor.check_call([
                COMMAND_CHROOT,
                abs_mountpoint,
                'eselect', 'news', 'read', '--quiet', 'all',
                ], env=env)

    def install_kernel(self, abs_mountpoint, env):
        self._set_package_keywords(abs_mountpoint, 'sys-kernel/vanilla-sources', '**')  # TODO ~arch
        self._set_package_use_flags(abs_mountpoint, 'sys-kernel/vanilla-sources', 'symlink')
        self._install_package_atoms(abs_mountpoint, env, ['sys-kernel/vanilla-sources'])
        self._executor.check_call([
                COMMAND_CHROOT, abs_mountpoint,
                'make', '-C', '/usr/src/linux', 'defconfig',
                ], env=env)
        shutil.copyfile(
                os.path.join(abs_mountpoint, 'usr/src/linux/.config'),
                os.path.join(abs_mountpoint, 'usr/src/linux/.config.defconfig'),
                )
        self._executor.check_call([
                COMMAND_CHROOT, abs_mountpoint,
                'make',
                '-C', '/usr/src/linux',
                '-j2',
                ], env=env)
        self._executor.check_call([
                COMMAND_CHROOT, abs_mountpoint,
                'make',
                '-C', '/usr/src/linux',
                'modules_install', 'install',
                ], env=env)

    @classmethod
    def add_parser_to(clazz, distros):
        gentoo = distros.add_parser(clazz.DISTRO_KEY, help=clazz.DISTRO_NAME_LONG)
        gentoo.set_defaults(**{DISTRO_CLASS_FIELD: clazz})

        GentooBootstrapper.add_arguments_to(gentoo)

    @classmethod
    def create(clazz, messenger, executor, options):
        return clazz(
                messenger,
                executor,
                os.path.abspath(options.cache_dir),
                options.mirror_url,
                options.max_age_days,
                options.stage3_date,
                options.repository_date,
                os.path.abspath(options.resolv_conf),
                )
