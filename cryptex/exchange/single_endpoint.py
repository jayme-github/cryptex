import time
import hmac
from hashlib import sha512
from urllib import urlencode
from urlparse import urljoin
from decimal import Decimal
import itertools
import requests

from cryptex.exception import APIException


class SingleEndpoint(object):
    ''' Simple enpoint for performing any kind of get request '''
    session = requests

    def _init_http_session(self):
        '''
        Initialise requests session
        '''
        self.session = requests.Session()

    def perform_get_request(self, method='', params={}):
        request_url = type(self).API_ENDPOINT
        if method:
            if not request_url.endswith('/'):
                request_url += '/'
            request_url = urljoin(request_url, method)
        r = self.session.get(request_url, params=params)
        content = r.json(parse_float=Decimal)

        if not content:
            raise APIException('Empty response')

        if 'success' in content:
            if int(content['success']) == 0:
                raise APIException(content['error'])
        if 'return' in content:
            return content['return']
        else:
            return content

class SignedSingleEndpoint(object):
    """
    BTC-e and Cryptsy both employ the same API auth scheme and format.  There 
    exists a single endpoint. Different actions are performed by passing a 
    "method" parameter.  All requests are POST. All reponses are json, 
    returing an object with keys "success" and "return" (if successful).
    """
    session = requests
    # Possible thread safe implementation for "as small as possible" nonce
    # https://mail.python.org/pipermail/python-dev/2004-February/042391.html
    _get_nonce = itertools.count().next

    def _set_nonce(self, nonce):
        self._get_nonce = itertools.count(start=nonce).next

    def _init_http_session(self):
        '''
        Initialise requests session
        '''
        self.session = requests.Session()

    def get_request_params(self, method, data):
        payload = {
            'method': method,
            'nonce': self._get_nonce()
        }
        payload.update(data)
        signature = hmac.new(self.secret, urlencode(payload), 
            sha512).hexdigest()
        
        headers = {
            'Sign': signature, 
            'Key': self.key
        }
        return (payload, headers)

    def perform_request(self, method, data={}):
        payload, headers = self.get_request_params(method, data)
        r = self.session.post(type(self).API_ENDPOINT, data=payload, headers=headers)
        content = r.json(parse_float=Decimal)

        # Cryptsy returns success as a string, BTC-e as a int
        if int(content['success']) != 1:
            raise APIException(content['error'])

        # Cryptsy's createorder response is stupidly broken
        if method == 'createorder':
            content['return'] = {
                'orderid': content['orderid'],
                'moreinfo': content['moreinfo']
            }
        return content['return']
