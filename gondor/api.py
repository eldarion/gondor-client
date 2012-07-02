import base64
import urllib2

from gondor import http


def make_api_call(config, url, params=None, extra_handlers=None):
    handlers = [
        http.HTTPSHandler,
    ]
    if extra_handlers is not None:
        handlers.extend(extra_handlers)
    opener = urllib2.build_opener(*handlers)
    request = urllib2.Request(url, params)
    request.add_unredirected_header(
        "Authorization",
        "Basic %s" % base64.b64encode("%s:%s" % (config["auth.username"], config["auth.key"])).strip()
    )
    return opener.open(request)
