from urllib.parse import parse_qsl, urlsplit

from authlib.oauth2.rfc6749 import OAuth2Request
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload


class CanonicalRequest(OAuth2Request):
    """Concrete Authlib payload with a trusted configured issuer URI."""

    def __init__(self, method, uri, body=None, headers=None):
        super().__init__(method, uri, headers=headers)
        self._args = dict(parse_qsl(urlsplit(uri).query, keep_blank_values=True))
        self._form = body or {}
        self.payload = BasicOAuth2Payload({**self._args, **self._form})

    @property
    def args(self):
        return self._args

    @property
    def form(self):
        return self._form
