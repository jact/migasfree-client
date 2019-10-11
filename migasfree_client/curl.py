# -*- coding: utf-8 -*-

# Copyright (c) 2011-2019 Jose Antonio Chavarría <jachavar@gmail.com>
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

"""
Based in http://stackoverflow.com/questions/472179/how-to-read-the-header-with-pycurl

SSL info:
* http://www.daimi.au.dk/~mailund/association-mapping/download/deb-packages/MiG/server/TestCurl.py

* http://www.dmclaughlin.com/2011/04/14/ssl-client-authentication-with-python/

* http://kelleyk.com/post/8446569648/adventures-with-libcurl-and-pycurl-post-data-ssl

* http://lists.planet-lab.org/pipermail/devel/2007-June/001963.html

* http://curl.haxx.se/docs/sslcerts.html

* /etc/ssl/certs/Makefile -> /etc/pki/tls/certs/Makefile

* http://realmike.org/blog/2011/01/02/ssl-certificate-error-with-gwibber-and-identi-ca-on-ubuntu/

* http://gagravarr.org/writing/openssl-certs/others.shtml
"""

__author__ = 'Jose Antonio Chavarría'

import os
try:
    import pycurl
except ImportError:
    raise SystemExit('migasfree client requires PycURL 7.19 or later.')

from . import utils


class Storage(object):
    def __init__(self):
        self.contents = ''

    def store(self, data):
        self.contents += data

    def __str__(self):
        return self.contents


class Curl(object):
    DEBUG = 0

    def __init__(
        self,
        url='',
        post=None,
        proxy='',
        accept_lang='en-US',
        cert=None,
        timeout=0
    ):
        self.url = url
        self.post = post
        self.proxy = proxy
        self.accept_lang = accept_lang

        self.error = None
        self.errno = 0
        self.http_code = 0

        # http://tools.ietf.org/html/rfc7231#section-5.5.3
        self.user_agent = 'migasfree-client/%s' % utils.get_mfc_release()

        self.body = Storage()
        self.header = Storage()

        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.TIMEOUT, timeout)
        self.curl.setopt(pycurl.WRITEFUNCTION, self.body.store)
        self.curl.setopt(pycurl.HEADERFUNCTION, self.header.store)
        self.curl.setopt(pycurl.FOLLOWLOCATION, 1)
        self.curl.setopt(pycurl.HTTPGET, 1)

        if self.url.startswith('https://'):  # server over SSL
            self.curl.setopt(pycurl.SSL_VERIFYPEER, 0)  # do not check the server's cert
            self.curl.setopt(pycurl.SSL_VERIFYHOST, 0)

            # Set certificate path and verifications
            if cert is not None and os.path.exists(cert):
                self.curl.setopt(pycurl.CAINFO, cert)
                try:
                    import certifi

                    self.curl.setopt(pycurl.CAINFO, certifi.where())
                    self.curl.setopt(pycurl.SSL_VERIFYPEER, 1)
                    self.curl.setopt(pycurl.SSL_VERIFYHOST, 2)
                except ImportError:
                    pass

        if self.DEBUG:
            self.curl.setopt(pycurl.VERBOSE, 1)
            self.curl.setopt(pycurl.DEBUGFUNCTION, self._test)

    def _test(self, debug_type, debug_msg):
        print('debug(%d): %s' % (debug_type, debug_msg))

    def run(self):
        self.curl.setopt(pycurl.HTTPHEADER, [
            'Accept-Language: %s' % self.accept_lang,
            'User-Agent: %s' % self.user_agent,
            'Expect:',
        ])
        self.curl.setopt(pycurl.URL, self.url)

        if self.proxy:
            self.curl.setopt(pycurl.PROXY, self.proxy)

        if self.post:
            self.curl.setopt(pycurl.POST, 1)
            self.curl.setopt(pycurl.HTTPPOST, self.post)

        try:
            self.curl.perform()
            self.http_code = self.curl.getinfo(pycurl.HTTP_CODE)
            self.error = None
        except pycurl.error as e:
            self.error = self.curl.errstr()
            self.errno = e[0]
        finally:
            self.curl.close()
