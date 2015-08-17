import email.generator
import io
import os
import re
import socket
import ssl

import six
from six.moves import http_client

if six.PY3:
    from urllib.parse import urlencode
    from urllib.request import BaseHandler, HTTPHandler, HTTPSHandler
else:
    from urllib import urlencode
    from urllib2 import BaseHandler, HTTPHandler, HTTPSHandler

ucb = None  # upload callback
ubs = None  # upload bytes sent
ubt = None  # upload bytes total


GONDOR_IO_CRT = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    "ssl", "gondor.io.crt"
)


class CertificateError(ValueError):
    pass


def _dnsname_to_pat(dn):
    pats = []
    for frag in dn.split(r'.'):
        if frag == '*':
            # When '*' is a fragment by itself, it matches a non-empty dotless
            # fragment.
            pats.append('[^.]+')
        else:
            # Otherwise, '*' matches any dotless fragment.
            frag = re.escape(frag)
            pats.append(frag.replace(r'\*', '[^.]*'))
    return re.compile(r'\A' + r'\.'.join(pats) + r'\Z', re.IGNORECASE)


def match_hostname(cert, hostname):
    """Verify that *cert* (in decoded format as returned by
    SSLSocket.getpeercert()) matches the *hostname*.  RFC 2818 rules
    are mostly followed, but IP addresses are not accepted for *hostname*.

    CertificateError is raised on failure. On success, the function
    returns nothing.
    """
    if not cert:
        raise ValueError("empty or no certificate")
    dnsnames = []
    san = cert.get('subjectAltName', ())

    for key, value in san:
        if key == 'DNS':
            if _dnsname_to_pat(value).match(hostname):
                return
            dnsnames.append(value)

    if not san:
        # The subject is only checked when subjectAltName is empty
        for sub in cert.get('subject', ()):
            for key, value in sub:
                # XXX according to RFC 2818, the most specific Common Name
                # must be used.
                if key == 'commonName':
                    if _dnsname_to_pat(value).match(hostname):
                        return
                    dnsnames.append(value)
    if len(dnsnames) > 1:
        raise CertificateError("hostname {!r} doesn't match either of {}".format(hostname, ", ".join(map(repr, dnsnames))))
    elif len(dnsnames) == 1:
        raise CertificateError("hostname {!r} doesn't match {!r}".format(hostname, dnsnames[0]))
    else:
        raise CertificateError("no appropriate commonName or subjectAltName fields were found")


class HTTPSConnection(http_client.HTTPConnection):
    """
    This class allows communication via SSL.
    Ported from Python 3.2. Does not follow Eldarion code-style.
    """

    default_port = 443

    def __init__(self, host, port=None, key_file=None, cert_file=None,
                 strict=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        http_client.HTTPConnection.__init__(self, host, port, strict, timeout)
        self.key_file = key_file
        self.cert_file = cert_file

    def connect(self):
        """
        Connect to a host on a given (SSL) port.
        """
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = ssl.wrap_socket(
            sock, self.key_file, self.cert_file,
            ca_certs=GONDOR_IO_CRT, cert_reqs=ssl.CERT_REQUIRED
        )
        try:
            match_hostname(self.sock.getpeercert(), self.host)
        except Exception:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
            raise


class GondorHTTPSHandler(HTTPSHandler):

    def https_open(self, request):
        return self.do_open(HTTPSConnection, request)


def UploadProgressHandler(pb, ssl=False):
    if ssl:
        conn_class = HTTPSConnection
        handler_class = HTTPSHandler
    else:
        conn_class = http_client.HTTPConnection
        handler_class = HTTPHandler
    class HTTPConnection(conn_class):
        def send(self, buf):
            global ubt, ubs
            ubs = 0
            ubt = send_length = len(buf)
            cs = 8192
            prev = 0
            while ubs < send_length:
                percentage = int(round((float(ubs) / ubt) * 100))
                pb.update(percentage)
                if percentage != prev:
                    pb.display()
                    prev = percentage
                conn_class.send(self, buf[ubs:ubs + cs])
                ubs += cs
            # once we are done uploading the file set the progress bar to
            # 100% as sometimes it never gets full
            pb.update(100)
            pb.display()
    class _UploadProgressHandler(handler_class):
        handler_order = HTTPHandler.handler_order - 9  # run second
        if ssl:
            def https_open(self, request):
                return self.do_open(HTTPConnection, request)
        else:
            def http_open(self, request):
                return self.do_open(HTTPConnection, request)
    return _UploadProgressHandler


class MultipartPostHandler(BaseHandler):
    handler_order = HTTPHandler.handler_order - 10  # run first

    def http_request(self, request):
        data = request.data
        if data is not None and not isinstance(data, str):
            params, files = [], []
            try:
                if isinstance(data, dict):
                    data = six.iteritems(data)
                for key, value in data:
                    if hasattr(value, "read"):
                        files.append((key, value))
                    else:
                        params.append((key, value))
            except TypeError:
                raise TypeError("not a valid non-string sequence or mapping object")
            if not files:
                data = urlencode(params, 1).encode("utf-8")
            else:
                boundary, data = self.multipart_encode(params, files)
                request.add_unredirected_header("Content-Type", b'multipart/form-data; boundary="' + boundary + b'"')
            request.data = data
        return request

    https_request = http_request

    def multipart_encode(self, params, files, boundary=None, buf=None):
        if boundary is None:
            boundary = email.generator._make_boundary()
            boundary = boundary.encode("latin-1")
        if buf is None:
            buf = io.BytesIO()
        for key, value in params:
            if isinstance(key, six.string_types):
                key = key.encode("latin-1")
            if isinstance(value, six.string_types):
                value = value.encode("latin-1")
            buf.write(b"--" + boundary + b"\r\n")
            buf.write(b'Content-Disposition: form-data; name="' + key + b'"')
            buf.write(b"\r\n\r\n" + value + b"\r\n")
        for key, fd in files:
            if isinstance(key, six.string_types):
                key = key.encode("latin-1")
            filename = fd.name.split("/")[-1].encode("latin-1")
            buf.write(b"--" + boundary + b"\r\n")
            buf.write(b'Content-Disposition: form-data; name="' + key + b'"; filename="' + filename + b'"\r\n')
            buf.write(b"Content-Type: application/octet-stream")
            buf.write(b"\r\n\r\n")
            buf.write(fd.read())
            buf.write(b"\r\n")
        buf.write(b"--" + boundary + b"--\r\n\r\n")
        buf = buf.getvalue()
        return boundary, buf
