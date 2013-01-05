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
    request = Request(url, params)
    request.add_unredirected_header(
        "Authorization",
        "Basic %s" % base64.b64encode("%s:%s" % (config["auth.username"], config["auth.key"])).strip()
    )
    return opener.open(request)
