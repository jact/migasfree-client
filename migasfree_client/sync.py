# -*- coding: UTF-8 -*-

# Copyright (c) 2011-2017 Jose Antonio Chavarría <jachavar@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import errno
import json
import time
import tempfile
import requests
import cups
import socket

# http://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
import signal

import gettext
_ = gettext.gettext

import logging
logger = logging.getLogger(__name__)

from datetime import datetime

from . import (
    settings,
    utils,
    printcolor,
    network,
)

from .command import MigasFreeCommand
from .devices import Printer

__author__ = 'Jose Antonio Chavarría <jachavar@gmail.com>'
__license__ = 'GPLv3'
__all__ = 'MigasFreeSync'


class MigasFreeSync(MigasFreeCommand):
    APP_NAME = 'Migasfree'

    _graphic_user = None

    _error_file_descriptor = None

    _pms_status_ok = True  # indicates the status of transactions with PMS

    def __init__(self):
        self._user_is_not_root()

        signal.signal(signal.SIGINT, self._exit_gracefully)
        signal.signal(signal.SIGQUIT, self._exit_gracefully)
        signal.signal(signal.SIGTERM, self._exit_gracefully)

        MigasFreeCommand.__init__(self)
        self._init_environment()

    def _init_environment(self):
        graphic_pid, graphic_process = utils.get_graphic_pid()
        logger.debug('Graphic pid: %s', graphic_pid)
        logger.debug('Graphic process: %s', graphic_process)

        if not graphic_pid:
            self._graphic_user = os.environ.get('USER')
            print(_('No detected graphic process'))
        else:
            self._graphic_user = utils.get_graphic_user(graphic_pid)
            user_display = utils.get_user_display_graphic(graphic_pid)
            logger.debug('Graphic display: %s', user_display)

        logger.debug('Graphic user: %s', self._graphic_user)

    def _exit_gracefully(self, signal_number, frame):
        self._show_message(_('Killing %s before time!!!') % self.CMD)
        logger.critical('Exiting %s, signal: %s', self.CMD, signal_number)
        sys.exit(errno.EINPROGRESS)

    def _show_running_options(self):
        MigasFreeCommand._show_running_options(self)

        print('\t%s: %s' % (_('Graphic user'), self._graphic_user))
        print('')

    def _usage_examples(self):
        print('\n' + _('Examples:'))

        print('  ' + _('Register computer at server:'))
        print('\t%s register\n' % self.CMD)

        print('  ' + _('Synchronize computer with server:'))
        print('\t%s sync\n' % self.CMD)

        print('  ' + _('Search package:'))
        print('\t%s search bluefish\n' % self.CMD)

        print('  ' + _('Install package:'))
        print('\t%s install bluefish\n' % self.CMD)

        print('  ' + _('Purge package:'))
        print('\t%s purge bluefish\n' % self.CMD)

    def _write_error(self, msg, append=False):
        if append:
            _mode = 'a'
        else:
            _mode = 'wb'

        if not self._error_file_descriptor:
            self._error_file_descriptor = open(self.ERROR_FILE, _mode)

        self._error_file_descriptor.write('%s\n' % ('-' * 20))
        self._error_file_descriptor.write(
            '%s\n' % time.strftime("%Y-%m-%d %H:%M:%S")
        )
        self._error_file_descriptor.write('%s\n\n' % str(msg))

    @staticmethod
    def _show_message(msg):
        print('')
        printcolor.info(str(' ' + msg + ' ').center(76, '*'))

    @staticmethod
    def _eval_code(lang, code):
        code = code.replace('\r', '').strip()  # clean code
        logger.debug('Language code: %s', lang)
        logger.debug('Code: %s', code)

        filename = tempfile.mkstemp()[1]
        utils.write_file(filename, code)

        allowed_languages = [
            'bash',
            'python',
            'perl',
            'php',
            'ruby'
        ]

        if lang in allowed_languages:
            cmd = '{} {}'.format(lang, filename)
        else:
            cmd = ':'  # gracefully degradation

        ret, output, error = utils.timeout_execute(cmd)
        logger.debug('Executed command: %s', cmd)
        logger.debug('Output: %s', output)
        if ret != 0:
            logger.error('Error: %s', error)
            msg = _('Code "%s" with error: %s') % (code, _error)
            self._write_error(msg)

        try:
            os.remove(filename)
        except IOError:
            pass

        return output

    def _eval_attributes(self, properties):
        response = {
            'id': self._computer_id,
            'uuid': utils.get_hardware_uuid(),
            'name': self.migas_computer_name,
            'fqdn': socket.getfqdn(),
            'ip_address': network.get_network_info()['ip'],
            'sync_user': self._graphic_user,
            'sync_fullname': utils.get_user_info(
                self._graphic_user
            )['fullname'],
            'sync_attributes': {}
        }

        # properties converted in attributes
        self._show_message(_('Evaluating attributes...'))
        for item in properties:
            response['sync_attributes'][item['prefix']] = \
                self._eval_code(item['language'], item['code'])
            info = '{}: {}'.format(
                item['prefix'],
                response['sync_attributes'][item['prefix']]
            )
            if response['sync_attributes'][item['prefix']].strip() != '':
                self.operation_ok(info)
            else:
                self.operation_failed(info)
                self._write_error(
                    _('Error: property %s without value') % item['prefix']
                )

        return response

    def _eval_faults(self, fault_definitions):
        response = {
            'id': self._computer_id,
            'faults': {}
        }

        self._show_message(_('Executing faults...'))
        for item in fault_definitions:
            result = self._eval_code(item['language'], item['code'])
            info = '{}: {}'.format(item['name'], result)
            if result:
                # only send faults with output!!!
                response['faults'][item['name']] = result
                self.operation_failed(info)
            else:
                self.operation_ok(info)

        return response

    def get_repositories_url_template(self):
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_repositories_url_template']),
            safe=False,
            exit_on_error=False,
            debug=self._debug
        )
        response = response.replace('"', '')  # remove extra quotes
        logger.debug('Response get_repositories_url_template: {}'.format(response))

        return response

    def get_properties(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Getting properties...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_properties']),
            data={
                'id': self._computer_id
            },
            debug=self._debug
        )
        logger.debug('Response get_properties_id: %s', response)

        if 'error' in response:
            self.operation_failed(response['error']['info'])
            sys.exit(errno.ENODATA)

        self.operation_ok()

        return response

    def get_fault_definitions(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Getting fault definitions...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_fault_definitions']),
            data={
                'id': self._computer_id
            },
            debug=self._debug
        )
        logger.debug('Response get_fault_definitions: %s', response)

        if 'error' in response:
            self.operation_failed(response['error']['info'])
            sys.exit(errno.ENODATA)

        self.operation_ok()

        return response

    def get_repositories(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Getting repositories...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_repositories']),
            data={
                'id': self._computer_id
            },
            exit_on_error=False,
            debug=self._debug
        )
        logger.debug('Response get_repositories: %s', response)

        if 'error' in response:
            self.operation_failed(response['error']['info'])
            return []

        self.operation_ok()

        return response

    def get_mandatory_packages(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Getting mandatory packages...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_mandatory_packages']),
            data={
                'id': self._computer_id
            },
            exit_on_error=False,
            debug=self._debug
        )
        logger.debug('Response get_mandatory_packages: %s', response)

        if 'error' in response:
            if response['error']['code'] == requests.codes.not_found:
                self.operation_ok()
                return None
            else:
                self.operation_failed(response['error']['info'])
                sys.exit(errno.ENODATA)

        self.operation_ok()

        return response

    def get_devices(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Getting devices...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_devices']),
            data={
                'id': self._computer_id
            },
            exit_on_error=False,
            debug=self._debug
        )
        logger.debug('Response get_devices: %s', response)

        """
        response: {
            "logical": [{}, ...],
            "default": int
        }
        """

        if 'error' in response:
            if response['error']['code'] == requests.codes.not_found:
                self.operation_ok()
                return None
            else:
                self.operation_failed(response['error']['info'])
                sys.exit(errno.ENODATA)

        self.operation_ok()

        return response

    @staticmethod
    def _software_history(software):
        history = {}

        # if have been managed packages manually
        # information is uploaded to server
        if os.path.isfile(settings.SOFTWARE_FILE) \
                and os.stat(settings.SOFTWARE_FILE).st_size:
            diff_software = utils.compare_lists(
                open(
                    settings.SOFTWARE_FILE,
                    'U'
                ).read().splitlines(),  # not readlines!!!
                software
            )

            if diff_software:
                history = {
                    'installed': [x for x in diff_software if x.startswith('+')],
                    'uninstalled': [x for x in diff_software if x.startswith('-')],
                }
                logger.debug('Software diff: %s', history)

        return history

    def _upload_old_errors(self):
        """
        if there are old errors, upload them to server
        """
        if os.path.isfile(self.ERROR_FILE) \
                and os.stat(self.ERROR_FILE).st_size:
            self._show_message(_('Uploading old errors...'))
            response = self._url_request.run(
                url=self.api_endpoint(self.URLS['upload_errors']),
                data={
                    'id': self._computer_id,
                    'description': utils.read_file(self.ERROR_FILE)
                },
                debug=self._debug
            )
            logger.debug('Response _upload_old_errors: %s', response)
            self.operation_ok()
            os.remove(self.ERROR_FILE)

        self._error_file_descriptor = open(self.ERROR_FILE, 'wb')

    def _create_repositories(self):
        url_template = self.get_repositories_url_template()
        repos = self.get_repositories()

        self._show_message(_('Creating repositories...'))

        server = self.migas_server
        if self.migas_package_proxy_cache:
            server = '{}/{}'.format(self.migas_package_proxy_cache, server)

        ret = self.pms.create_repos(
            url_template,
            server,
            utils.slugify(unicode(self.migas_project)),
            repos
        )

        if ret:
            self.operation_ok()
        else:
            self._pms_status_ok = False
            msg = _('Error creating repositories: %s') % repos
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)

    def _clean_pms_cache(self):
        """
        clean cache of Package Management System
        """
        self._show_message(_('Getting repositories metadata...'))
        ret = self.pms.clean_all()

        if ret:
            self.operation_ok()
        else:
            msg = _('Error getting repositories metadata')
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)

    def _uninstall_packages(self, packages):
        self._show_message(_('Uninstalling packages...'))
        ret, error = self.pms.remove_silent(packages)
        if ret:
            self.operation_ok()
        else:
            self._pms_status_ok = False
            msg = _('Error uninstalling packages: %s') % error
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)

    def _install_mandatory_packages(self, packages):
        self._show_message(_('Installing mandatory packages...'))
        ret, error = self.pms.install_silent(packages)
        if ret:
            self.operation_ok()
        else:
            self._pms_status_ok = False
            msg = _('Error installing packages: %s') % error
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)

        return ret

    def _update_packages(self):
        self._show_message(_('Updating packages...'))
        ret, error = self.pms.update_silent()
        if ret:
            self.operation_ok()
        else:
            self._pms_status_ok = False
            msg = _('Error updating packages: %s') % error
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)

        return ret

    def hardware_capture_is_required(self):
        if not self._computer_id:
            self.get_computer_id()

        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['get_hardware_required']),
            data={
                'id': self._computer_id,
            },
            exit_on_error=False,
            debug=self._debug
        )
        logger.debug('Response hardware_capture_is_required: %s', response)

        if isinstance(response, dict) and 'error' in response:
            self.operation_failed(response['error']['info'])
            sys.exit(errno.ENODATA)

        return response.get('capture', False)

    def _update_hardware_inventory(self):
        if not self._computer_id:
            self.get_computer_id()

        self._show_message(_('Capturing hardware information...'))
        cmd = 'LC_ALL=C lshw -json'
        ret, output, error = utils.execute(cmd, interactive=False)
        if ret == 0:
            self.operation_ok()
        else:
            msg = _('lshw command failed: %s') % error
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)
            return

        hardware = json.loads(output)
        logger.debug('Hardware inventory: %s', hardware)

        self._show_message(_('Sending hardware information...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['upload_hardware']),
            data={
                'id': self._computer_id,
                'hardware': hardware
            },
            exit_on_error=False,
            debug=self._debug
        )
        logger.debug('Response upload_hardware: %s', response)

        if 'error' in response:
            msg = response['error']['info']
            self.operation_failed(msg)
            logger.error(msg)
            self._write_error(msg)
            return

        self.operation_ok()

    def _upload_execution_errors(self):
        self._error_file_descriptor.close()
        self._error_file_descriptor = None

        if os.stat(self.ERROR_FILE).st_size:
            self._show_message(_('Sending errors to server...'))
            self._url_request.run(
                url=self.api_endpoint(self.URLS['upload_errors']),
                data={
                    'id': self._computer_id,
                    'description': utils.read_file(self.ERROR_FILE)
                },
                debug=self._debug
            )
            self.operation_ok()

            if not self._debug:
                os.remove(self.ERROR_FILE)

    def upload_attributes(self):
        response = self.get_properties()

        attributes = self._eval_attributes(response)
        logger.debug('Attributes to send: %s', attributes)

        self._show_message(_('Uploading attributes...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['upload_attributes']),
            data=attributes,
            debug=self._debug
        )
        self.operation_ok()
        logger.debug('Response upload_attributes: %s', response)

        return response

    def upload_faults(self):
        response = self.get_fault_definitions()
        if len(response) > 0:
            data = self._eval_faults(response)
            logger.debug('Faults to send: %s', data)

            self._show_message(_('Uploading faults...'))
            response = self._url_request.run(
                url=self.api_endpoint(self.URLS['upload_faults']),
                data=data,
                debug=self._debug
            )
            self.operation_ok()
            logger.debug('Response upload_faults: %s', response)

        return response

    def _mandatory_pkgs(self):
        response = self.get_mandatory_packages()
        if not response:
            return

        if 'remove' in response:
            self._uninstall_packages(response['remove'])
        if 'install' in response:
            self._install_mandatory_packages(response['install'])

    def _upload_software(self, before, history):
        if not self._computer_id:
            self.get_computer_id()

        after = self.pms.query_all()
        utils.write_file(settings.SOFTWARE_FILE, '\n'.join(after))

        diff_software = utils.compare_lists(before, after)
        if diff_software:
            data = {
                'installed': [x for x in diff_software if x.startswith('+')],
                'uninstalled': [x for x in diff_software if x.startswith('-')],
            }
            logger.debug('Software diff: %s', data)

            if data['installed']:
                if 'installed' in history:
                    history['installed'].extend(data['installed'])
                else:
                    history['installed'] = data['installed']
            if data['uninstalled']:
                if 'uninstalled' in history:
                    history['uninstalled'].extend(data['uninstalled'])
                else:
                    history['uninstalled'] = data['uninstalled']

            print(_('Software diff: %s') % history)

        self._show_message(_('Uploading software...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['upload_software']),
            data={
                'id': self._computer_id,
                'inventory': after,
                'history': history
            },
            debug=self._debug
        )
        logger.debug('Response upload_software: %s', response)

        if 'error' in response:
            self.operation_failed(response['error']['info'])
            sys.exit(errno.ENODATA)

        self.operation_ok()

        return response

    def end_synchronization(self, start_date, consumer=''):
        if not consumer:
            consumer = self.CMD

        self._show_message(_('Ending synchronization...'))
        response = self._url_request.run(
            url=self.api_endpoint(self.URLS['upload_sync']),
            data={
                'id': self._computer_id,
                'start_date': start_date,
                'consumer': '{} {}'.format(consumer, utils.get_mfc_release()),
                'pms_status_ok': self._pms_status_ok
            },
            debug=self._debug
        )
        self.operation_ok()
        logger.debug('Response upload_sync: %s', response)

        return response

    def synchronize(self):
        start_date = datetime.now().isoformat()

        if not self._check_sign_keys():
            sys.exit(errno.EPERM)

        self._show_message(_('Connecting to migasfree server...'))

        self._upload_old_errors()
        self.upload_attributes()
        self.upload_faults()

        software_before = self.pms.query_all()
        logger.debug('Actual software: %s', software_before)

        software_history = self._software_history(software_before)

        self._create_repositories()
        self._clean_pms_cache()
        self._mandatory_pkgs()
        if self.migas_auto_update_packages is True:
            self._update_packages()

        self._upload_software(software_before, software_history)

        if self.hardware_capture_is_required():
            self._update_hardware_inventory()

        self._sync_logical_devices()

        self._upload_execution_errors()
        self.end_synchronization(start_date)
        self.end_of_transmission()
        self._show_message(_('Completed operations'))

    def _search(self, pattern):
        return self.pms.search(pattern)

    def _install_package(self, pkg):
        software_before = self.pms.query_all()
        software_history = self._software_history(software_before)

        self._show_message(_('Installing package: %s') % pkg)
        ret = self.pms.install(pkg)

        self._upload_software(software_before, software_history)
        self.end_of_transmission()

        return ret

    def _remove_package(self, pkg):
        software_before = self.pms.query_all()
        software_history = self._software_history(software_before)

        self._show_message(_('Removing package: %s') % pkg)
        ret = self.pms.remove(pkg)

        self._upload_software(software_before, software_history)
        self.end_of_transmission()

        return ret

    def _sync_logical_devices(self):
        devices = self.get_devices()
        if not devices:
            return

        for device in devices['logical']:
            if 'packages' in device and device['packages']:
                if not self._install_mandatory_packages(device['packages']):
                    return False

        logical_devices = {}  # key is id field
        for device in devices['logical']:
            if 'PRINTER' in device:
                dev = Printer(device['PRINTER'])
                logical_devices[int(dev.logical_id)] = dev

        conn = cups.Connection()
        if not conn:
            return

        printers = conn.getPrinters()
        for printer in printers:
            # check if printer is a migasfree printer (by format)
            if len(printers[printer]['printer-info'].split('__')) == 5:
                key = int(printers[printer]['printer-info'].split('__')[4])
                if key in logical_devices:
                    # relate real devices with logical ones by id
                    logical_devices[key].printer_name = printer
                    logical_devices[key].printer_data = printers[printer]
                else:
                    try:
                        self._send_message(_('Removing device: %s') % printer)
                        conn.deletePrinter(printer)
                        self.operation_ok()
                        logging.debug('Device removed: %s', printer)
                    except cups.IPPError:
                        _msg = _('Error removing device: %s') % printer
                        self.operation_failed(_msg)
                        logging.error(_msg)
                        self._write_error(_msg)

        for key in logical_devices:
            _printer_name = logical_devices[key].name

            if logical_devices[key].driver is None:
                _msg = _('Error: no driver defined for device %s. Please, configure feature %s, in the model %s %s, and project %s') % (
                    _printer_name,
                    logical_devices[key].info.split('__')[2],  # feature
                    logical_devices[key].info.split('__')[0],  # manufacturer
                    logical_devices[key].info.split('__')[1],  # model
                    self.migas_project
                )
                self.operation_failed(_msg)
                logging.error(_msg)
                self._write_error(_msg)
                continue

            if logical_devices[key].is_changed():
                self._send_message(_('Installing device: %s') % _printer_name)
                if logical_devices[key].install():
                    self.operation_ok()
                    logging.debug('Device installed: %s', _printer_name)
                else:
                    _msg = _('Error installing device: %s') % _printer_name
                    self.operation_failed(_msg)
                    logging.error(_msg)
                    self._write_error(_msg)

        # System default printer
        if devices['default'] != 0 and devices['default'] in logical_devices:
            _printer_name = logical_devices[devices['default']].name
            if Printer.get_printer_id(conn.getDefault()) != devices['default']:
                try:
                    self._send_message(_('Setting default device: %s') % _printer_name)
                    conn.setDefault(_printer_name)
                    self.operation_ok()
                except cups.IPPError:
                    _msg = _('Error setting default device: %s') % _printer_name
                    self.operation_failed(_msg)
                    logging.error(_msg)
                    self._write_error(_msg)

    def run(self, args=None):
        self._show_running_options()

        if not args or not hasattr(args, 'cmd'):
            self._usage_examples()
            sys.exit(os.EX_OK)

        if hasattr(args, 'debug') and args.debug:
            self._debug = True
            logger.setLevel(logging.DEBUG)

        if args.cmd == 'sync':
            if args.force_upgrade:
                self.migas_auto_update_packages = True

            utils.check_lock_file(self.CMD, self.LOCK_FILE)
            self.synchronize()
            utils.remove_file(self.LOCK_FILE)

            if not self._pms_status_ok:
                sys.exit(errno.EPROTO)
        elif args.cmd == 'register':
            self._register_computer()
        elif args.cmd == 'search':
            self._search(args.pattern)
        elif args.cmd == 'install':
            utils.check_lock_file(self.CMD, self.LOCK_FILE)
            self._install_package(' '.join(args.pkg_install))
            utils.remove_file(self.LOCK_FILE)
        elif args.cmd == 'purge':
            utils.check_lock_file(self.CMD, self.LOCK_FILE)
            self._remove_package(' '.join(args.pkg_purge))
            utils.remove_file(self.LOCK_FILE)

        sys.exit(os.EX_OK)