import errno
import os
import select
import ssl
import sys

from gondor.utils import stdin_buffer, confirm


def unix_run_poll(sock):
    with stdin_buffer() as stdin:
        while True:
            try:
                try:
                    rr, rw, er = select.select([sock, sys.stdin], [], [], 0.1)
                except select.error, e:
                    if e.args[0] == errno.EINTR:
                        continue
                    raise
                if sock in rr:
                    data = sock.recv(4096)
                    if not data:
                        break
                    while data:
                        n = os.write(sys.stdout.fileno(), data)
                        data = data[n:]
                if sys.stdin in rr:
                    data = os.read(sys.stdin.fileno(), 4096)
                    while data:
                        n = sock.send(data)
                        data = data[n:]
            except KeyboardInterrupt:
                sock.sendall(chr(3))


def win32_run_poll(sock):
    import ctypes
    win32 = ctypes.windll.kernel32
    winsock = ctypes.windll.Ws2_32
    WAIT_TIMEOUT = 0x00000102L
    FD_READ = 0x01
    FD_CLOSE = 0x20
    sev = winsock.WSACreateEvent()
    winsock.WSAEventSelect(sock.fileno(), sev, FD_READ | FD_CLOSE)
    hin = win32.GetStdHandle(-10)
    mode = ctypes.c_int(0)
    win32.GetConsoleMode(hin, ctypes.byref(mode))
    mode = mode.value
    mode = mode & (~0x0001) # disable processed input
    mode = mode & (~0x0002) # disable line input
    mode = mode & (~0x0004) # disable echo input
    win32.SetConsoleMode(hin, mode)
    handles = [hin, sev]
    handles = (ctypes.c_long*len(handles))(*handles)
    sock.settimeout(0.1)
    while True:
        i = win32.WaitForMultipleObjects(len(handles), handles, False, 1000)
        if i == WAIT_TIMEOUT:
            continue
        if handles[i] == hin:
            buf = ctypes.create_string_buffer(1024)
            bytes_read = ctypes.c_int(0)
            win32.ReadFile(hin, ctypes.byref(buf), 1024, ctypes.byref(bytes_read), None)
            sock.sendall(buf.value)
        if handles[i] == sev:
            win32.ResetEvent(sev)
            try:
                data = sock.recv(4096)
            except ssl.SSLError, e:
                if e.message == "The read operation timed out":
                    continue
            if not data:
                break
            sys.stdout.write(data)
            sys.stdout.flush()
