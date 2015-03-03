#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) 2011-2015 Jose Antonio Chavarría
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
#
# Author: Jose Antonio Chavarría <jachavar@gmail.com>

__author__ = 'Jose Antonio Chavarría'
__license__ = 'GPLv3'
__all__ = ('MigasFreeUpload', 'main')

import os
import sys
#import argparse
import optparse
import getpass
import errno

import gettext
_ = gettext.gettext

import logging
logger = logging.getLogger(__name__)

from . import (
    settings,
    utils,
    url_request
)

from .command import (
    MigasFreeCommand,
    __version__,
)


class MigasFreeUpload(MigasFreeCommand):
    CMD = 'migasfree-upload'  # /usr/bin/migasfree-upload

    PRIVATE_KEY = 'migasfree-packager.pri'

    _file = None
    _is_regular_file = False
    _directory = None
    _server_directory = None
    _create_repo = True

    def _usage_examples(self):
        print('\n' + _('Examples:'))

        print('  ' + _('Upload single package:'))
        print('\t%s -f archive.pkg' % self.CMD)
        print('\t%s --file=archive.pkg\n' % self.CMD)

        print('  ' + _('Upload single package but not create repository:'))
        print('\t%s -f archive.pkg -c ' % self.CMD)
        print('\t%s --file=archive.pkg --no-create-repo\n' % self.CMD)

        print('  ' + _('Upload a regular file:'))
        print('\t%s -f archive -r' % self.CMD)
        print('\t%s --file=archive --regular-file\n' % self.CMD)

        print('  ' + _('Upload package set:'))
        print('\t%s -d local_directory -n server_directory' % self.CMD)
        print('\t%s --dir=local_directory --name=server_directory\n' % self.CMD)

        print('  ' + _('Upload regular files:'))
        print('\t%s -d local_directory -n server_directory -c' % self.CMD)
        print('\t%s --dir=local_directory --name=server_directory --no-create-repo\n' % self.CMD)

    def _show_running_options(self):
        MigasFreeCommand._show_running_options(self)

        print('\t%s: %s' % (_('Version'), self.packager_version))
        print('\t%s: %s' % (_('Store'), self.packager_store))
        print('\t%s: %s' % (_('User'), self.packager_user))
        #print('\t%s: %s' % (_('Password'), self.packager_pwd))
        if self._file:
            print('\t%s: %s' % (_('File'), self._file))
            print('\t%s: %s' % (_('Regular file'), self._is_regular_file))
        if self._directory:
            print('\t%s: %s' % (_('Directory'), self._directory))
            print('\t%s: %s' % (_('Server directory'), self._server_directory))
        print('\t%s: %s' % (_('Create repository'), self._create_repo))
        print('')

    def _left_parameters(self):
        if not self.packager_user:
            self.packager_user = raw_input('%s: ' % _('User to upload at server'))
            if not self.packager_user:
                print(_('Empty user. Exiting %s.') % self.CMD)
                logger.info('Empty user in upload operation')
                sys.exit(errno.EAGAIN)

        if not self.packager_pwd:
            self.packager_pwd = getpass.getpass('%s: ' % _('User password'))

        if not self.packager_version:
            self.packager_version = raw_input('%s: ' % _('Version to upload at server'))
            if not self.packager_version:
                print(_('Empty version. Exiting %s.') % self.CMD)
                logger.info('Empty version in upload operation')
                sys.exit(errno.EAGAIN)

        if not self.packager_store:
            self.packager_store = raw_input('%s: ' % _('Store to upload at server'))
            if not self.packager_store:
                print(_('Empty store. Exiting %s.') % self.CMD)
                logger.info('Empty store in upload operation')
                sys.exit(errno.EAGAIN)

    def _upload_file(self):
        logger.debug('Upload file operation...')
        if not os.path.isfile(self._file):
            print(_('File not found'))
            logger.error('File not found %s', self._file)
            sys.exit(errno.ENOENT)

        self._check_sign_keys()

        logger.debug('Uploading file: %s', self._file)
        _ret = self._url_request.run(
            'upload_server_package',
            data={
                'version': self.packager_version,
                'store': self.packager_store,
                'source': self._is_regular_file
            },
            upload_file=os.path.abspath(self._file)
        )

        logger.debug('Uploading response: %s', _ret)
        if self._debug:
            print('Response: %s' % _ret)

        if _ret['errmfs']['code'] != server_errors.ALL_OK:
            _error_info = server_errors.error_info(_ret['errmfs']['code'])
            print(_error_info)
            logger.error('Uploading file error: %s', _error_info)
            sys.exit(errno.EINPROGRESS)

        return self._create_repository()

    def _upload_set(self):
        logger.debug('Upload set operation...')
        if not os.path.isdir(self._directory):
            print(_('Directory not found'))
            logger.error('Directory not found %s', self._directory)
            sys.exit(errno.ENOENT)

        self._check_sign_keys()

        for _root, _subfolders, _files in os.walk(self._directory):
            for _file in _files:
                _filename = os.path.join(_root, _file)

                if os.path.isfile(_filename):
                    logger.debug('Uploading server set: %s', _filename)
                    if self._debug:
                        print('Uploading file: %s' % os.path.abspath(_filename))

                    _ret = self._url_request.run(
                        'upload_server_set',
                        data={
                            'version': self.packager_version,
                            'store': self.packager_store,
                            'packageset': self._server_directory,
                            'path': os.path.dirname(
                                os.path.join(
                                    _root,
                                    _file
                                )[len(self._directory) + 1:]
                            )
                        },
                        upload_file=os.path.abspath(_filename)
                    )

                    logger.debug('Uploading set response: %s', _ret)
                    if self._debug:
                        print('Response: %s' % _ret)

                    if _ret['errmfs']['code'] != server_errors.ALL_OK:
                        _error_info = server_errors.error_info(
                            _ret['errmfs']['code']
                        )
                        print(_error_info)
                        logger.error('Uploading set error: %s', _error_info)
                        sys.exit(errno.EINPROGRESS)

        return self._create_repository()

    def _create_repository(self):
        if not self._create_repo:
            return True

        logger.debug('Creating repository operation...')

        if self._file:
            _packageset = self._file
        else:
            _packageset = self._server_directory

        _ret = self._url_request.run(
            'create_repositories_of_packageset',
            data={
                'version': self.packager_version,
                'packageset': _packageset
            }
        )

        logger.debug('Creating repository response: %s', _ret)
        if self._debug:
            print('Response: %s' % _ret)

        if _ret['errmfs']['code'] != server_errors.ALL_OK:
            _error_info = server_errors.error_info(_ret['errmfs']['code'])
            print(_error_info)
            logger.error('Creating repository error: %s', _error_info)
            sys.exit(errno.EINPROGRESS)

        return True

    def run(self):
        _program = 'migasfree upload'
        parser = optparse.OptionParser(
            description=_program,
            prog=self.CMD,
            version=__version__,
            usage='%prog options'
        )

        print(_('%(program)s version: %(version)s') % {
            'program': _program,
            'version': __version__
        })

        # migasfree-upload {-f file [--regular-file] | -d dir [-n name]}
        #  [[-u user] [-p pwd] [--main-version version] [-s store] [--no-create-repo]]

        parser.add_option("--file", "-f", action="store",
            help=_('File to upload at server'))
        parser.add_option("--regular-file", "-r", action="store_true",
            help=_('File is not a software package'))

        parser.add_option("--dir", "-d", action="store",
            help=_('Directory with files to upload at server'))
        parser.add_option("--name", "-n", action="store",
            help=_('Name of the directory at server'))

        parser.add_option("--user", "-u", action="store",
            help=_('Authorized user to upload at server'))
        parser.add_option("--pwd", "-p", action="store",
            help=_('User password'))
        parser.add_option("--main-version", "-m", action="store",
            help=_('Version to upload files'))
        parser.add_option("--store", "-s", action="store",
            help=_('Main version repository at server'))
        parser.add_option("--no-create-repo", "-c", action="store_true",
            help=_('No create repository after upload file at server'))

        options, arguments = parser.parse_args()

        # check restrictions
        if not options.file and not options.dir:
            self._usage_examples()
            parser.error(_('File or Dir options are mandatory!!!'))
        if options.file and options.dir:
            self._usage_examples()
            parser.error(_('File and Dir options are exclusive!!!'))
        if options.regular_file and options.dir:
            self._usage_examples()
            parser.error(_('This option does not apply with Dir option!!!'))
        if options.name and options.file:
            self._usage_examples()
            parser.error(_('This option does not apply with File option!!!'))

        utils.check_lock_file(self.CMD, self.LOCK_FILE)

        # assign config options
        if options.user:
            self.packager_user = options.user
        if options.pwd:
            self.packager_pwd = options.pwd
        if options.main_version:
            self.packager_version = options.main_version
        if options.store:
            self.packager_store = options.store

        if options.no_create_repo:
            self._create_repo = not options.no_create_repo

        # actions dispatcher
        if options.file:
            self._file = options.file
            self._is_regular_file = (options.regular_file is True)
            if self._is_regular_file:
                self._create_repo = False
        elif options.dir:
            self._directory = options.dir
            if options.name:
                self._server_directory = options.name
            else:
                self._server_directory = options.dir
        else:
            parser.print_help()
            self._usage_examples()

        self._left_parameters()
        self.auto_register_user = self.packager_user
        self.auto_register_password = self.packager_pwd
        self.auto_register_end_point = 'public/keys/packager/'

        self._show_running_options()

        if self._file:
            self._upload_file()
        else:
            self._upload_set()

        utils.remove_file(self.LOCK_FILE)

        sys.exit(os.EX_OK)  # no error


def main():
    mfu = MigasFreeUpload()
    mfu.run()

if __name__ == "__main__":
    main()
