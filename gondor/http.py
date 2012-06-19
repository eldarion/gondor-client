import httplib
import mimetools
import os
import re
import socket
import ssl
import sys
import time
import urllib
import urllib2

from cStringIO import StringIO

ucb = None # upload callback
ubs = None # upload bytes sent
ubt = None # upload bytes total


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
        raise CertificateError("hostname %r "
            "doesn't match either of %s"
            % (hostname, ', '.join(map(repr, dnsnames))))
    elif len(dnsnames) == 1:
        raise CertificateError("hostname %r "
            "doesn't match %r"
            % (hostname, dnsnames[0]))
    else:
        raise CertificateError("no appropriate commonName or "
            "subjectAltName fields were found")


class HTTPSConnection(httplib.HTTPConnection):
    """
    This class allows communication via SSL.
    Ported from Python 3.2. Does not follow Eldarion code-style.
    """
    
    default_port = 443
    
    def __init__(self, host, port=None, key_file=None, cert_file=None,
                 strict=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        httplib.HTTPConnection.__init__(self, host, port, strict, timeout)
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


class HTTPSHandler(urllib2.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(HTTPSConnection, request)


def UploadProgressHandler(pb, ssl=False):
    if ssl:
        conn_class = HTTPSConnection
        handler_class = urllib2.HTTPSHandler
    else:
        conn_class = httplib.HTTPConnection
        handler_class = urllib2.HTTPHandler
    class HTTPConnection(conn_class):
        def send(self, buf):
            global ubt, ubs
            ubs = 0
            ubt = send_length = len(buf)
            cs = 8192
            prev = 0
            while ubs < send_length:
                percentage = int(round((float(ubs) / ubt) * 100))
                pb.updateAmount(percentage)
                if percentage != prev:
                    sys.stdout.write("%s\r" % pb)
                    sys.stdout.flush()
                    prev = percentage
                t1 = time.time()
                conn_class.send(self, buf[ubs:ubs+cs])
                ubs += cs
                t2 = time.time()
            # once we are done uploading the file set the progress bar to
            # 100% as sometimes it never gets full
            pb.updateAmount(100)
            sys.stdout.write("%s\r" % pb)
            sys.stdout.flush()
    class _UploadProgressHandler(handler_class):
        handler_order = urllib2.HTTPHandler.handler_order - 9 # run second
        if ssl:
            def https_open(self, request):
                return self.do_open(HTTPConnection, request)
        else:
            def http_open(self, request):
                return self.do_open(HTTPConnection, request)
    return _UploadProgressHandler


class MultipartPostHandler(urllib2.BaseHandler):
    handler_order = urllib2.HTTPHandler.handler_order - 10 # run first
    
    def http_request(self, request):
        data = request.get_data()
        if data is not None and not isinstance(data, str):
            params, files = [], []
            try:
                if isinstance(data, dict):
                    data = data.iteritems()
                for key, value in data:
                    if hasattr(value, "read"):
                        files.append((key, value))
                    else:
                        params.append((key, value))
            except TypeError:
                raise TypeError("not a valid non-string sequence or mapping object")
            if not files:
                data = urllib.urlencode(params, 1)
            else:
                boundary, data = self.multipart_encode(params, files)
                request.add_unredirected_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
            request.add_data(data)
        return request
    
    https_request = http_request
    
    def multipart_encode(self, params, files, boundary=None, buf=None):
        if boundary is None:
            boundary = mimetools.choose_boundary()
        if buf is None:
            buf = StringIO()
        for key, value in params:
            buf.write("--%s\r\n" % boundary)
            buf.write('Content-Disposition: form-data; name="%s"' % key)
            buf.write("\r\n\r\n" + value + "\r\n")
        for key, fd in files:
            filename = fd.name.split("/")[-1]
            buf.write("--%s\r\n" % boundary)
            buf.write('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (key, filename))
            buf.write("Content-Type: application/octet-stream\r\n")
            buf.write("\r\n" + fd.read() + "\r\n")
        buf.write("--" + boundary + "--\r\n\r\n")
        buf = buf.getvalue()
        return boundary, buf
