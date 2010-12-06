import httplib
import mimetools
import mimetypes
import os
import stat
import sys
import time
import urllib
import urllib2

from cStringIO import StringIO


ucb = None # upload callback
ubs = None # upload bytes sent
ubt = None # upload bytes total


def ucb(ubt, ubs):
    text = "Pushing tarball to Gondor... "
    sys.stdout.write("\r%s[%.0f%%]  " % (text, (float(ubs) / ubt) * 100))


class HTTPConnection(httplib.HTTPConnection):
    
    def send(self, buf):
        global ubt, ubs
        ubs = 0
        ubt = send_length = len(buf)
        cs = 8192
        while ubs < send_length:
            if ucb:
                ucb(ubt, ubs)
            sys.stdout.flush()
            t1 = time.time()
            httplib.HTTPConnection.send(self, buf[ubs:ubs+cs])
            ubs += cs
            t2 = time.time()
        if ucb:
            ucb(1, 1)


class UploadProgressHandler(urllib2.HTTPHandler):
    
    def http_open(self, request):
        return self.do_open(HTTPConnection, request)


class MultipartPostHandler(urllib2.BaseHandler):
    handler_order = urllib2.HTTPHandler.handler_order - 10 # needed to run first
    
    def http_request(self, request):
        data = request.get_data()
        if data is not None and not isinstance(data, str):
            params, files = [], []
            try:
                 for key, value in data.items():
                     if isinstance(value, file):
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
            file_size = os.fstat(fd.fileno())[stat.ST_SIZE]
            filename = fd.name.split("/")[-1]
            contenttype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            buf.write("--%s\r\n" % boundary)
            buf.write('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (key, filename))
            buf.write("Content-Type: %s\r\n" % contenttype)
            # buffer += "Content-Length: %s\r\n" % file_size
            fd.seek(0)
            buf.write("\r\n" + fd.read() + "\r\n")
        buf.write("--" + boundary + "--\r\n\r\n")
        buf = buf.getvalue()
        return boundary, buf
