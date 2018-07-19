# -*- coding: utf-8 -*-

# Copyright (c) 2011-2018 Jose Antonio Chavarría <jachavar@gmail.com>
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

__author__ = "Jose Antonio Chavarría"
__license__ = 'GPLv3'

import sys
import errno
import jose

from Crypto.PublicKey import RSA

from .utils import read_file
from . import settings

import logging
try:
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s',
        level=logging.ERROR,
        filename=settings.LOG_FILE
    )
except IOError:
    print('User has insufficient privileges to execute this command')
    sys.exit(errno.EACCES)
logger = logging.getLogger(__name__)


def sign(claims, priv_key):
    """
    string sign(dict claims, string priv_key)
    """
    rsa_key = RSA.importKey(read_file(priv_key))
    jwk = {'k': rsa_key.exportKey('PEM')}

    jws = jose.sign(claims, jwk, alg='RS256')  # Asymmetric!!!
    jwt = jose.serialize_compact(jws)

    return jwt


def verify(jwt, pub_key):
    """
    dict verify(string jwt, string pub_key)
    """
    rsa_key = RSA.importKey(read_file(pub_key))
    jwk = {'k': rsa_key.exportKey('PEM')}
    try:
        jwe = jose.deserialize_compact(jwt)
        # FIXME validate_claims=True!!!
        return jose.verify(jwe, jwk, alg='RS256', validate_claims=False)
    except:
        # DEBUG
        # import sys, traceback
        # traceback.print_exc(file=sys.stdout)
        return None


def encrypt(claims, pub_key):
    """
    string encrypt(dict claims, string pub_key)
    """
    rsa_key = RSA.importKey(read_file(pub_key))
    pub_jwk = {'k': rsa_key.publickey().exportKey('PEM')}

    jwe = jose.encrypt(claims, pub_jwk)
    jwt = jose.serialize_compact(jwe)

    return jwt


def decrypt(jwt, priv_key):
    """
    string decrypt(string jwt, string priv_key)
    """
    rsa_key = RSA.importKey(read_file(priv_key))
    priv_jwk = {'k': rsa_key.exportKey('PEM')}
    try:
        jwe = jose.deserialize_compact(jwt)
        return jose.decrypt(jwe, priv_jwk)
    except:
        return None


def wrap(data, sign_key, encrypt_key):
    """
    string wrap(dict data, string sign_key, string encrypt_key)
    """
    claims = {
        'data': data,
        'sign': sign(data, sign_key)
    }
    return encrypt(claims, encrypt_key)


def unwrap(data, decrypt_key, verify_key):
    """
    dict unwrap(string data, string decrypt_key, string verify_key)
    """
    jwt = decrypt(data, decrypt_key)
    jws = verify(jwt.claims['sign'], verify_key)
    if jws:
        return jwt.claims['data']

    return None
