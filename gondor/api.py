import base64

import six

if six.PY3:
    from urllib.request import build_opener, Request
else:
    from urllib2 import build_opener, Request

from gondor import http


def make_api_call(config, url, params=None, extra_handlers=None):
    handlers = [
        http.GondorHTTPSHandler,
    ]
    if extra_handlers is not None:
        handlers.extend(extra_handlers)
    opener = build_opener(*handlers)
    if isinstance(params, six.string_types):
        params = six.b(params)
    request = Request(url, params)
    credentials = "{}:{}".format(config["auth.username"], config["auth.key"])
    b64_credentials = base64.b64encode(credentials.encode("latin-1")).strip()
    request.add_unredirected_header(
        "Authorization",
        "Basic {}".format(b64_credentials.decode("latin-1")).encode("latin-1")
    )
    return opener.open(request)
