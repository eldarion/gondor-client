import errno
import os
import select
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
    sys.stderr.write("WARNING: Windows support for this command is broken.\n")
    if not confirm("Would you like to run it anyways?"):
        sys.exit(0)
    import win32api, win32console, win32event, win32file
    sock_event = win32event.CreateEvent(None, True, False, None)
    win32file.WSAEventSelect(sock.fileno(), sock_event, win32file.FD_CLOSE | win32file.FD_READ)
    import ctypes
    hin = win32.GetStdHandle(-10)
    mode = ctypes.c_int(0)
    win32.GetConsoleMode(hin, ctypes.byref(mode))
    mode = mode.value
    mode = mode & (~0x0001) # disable processed input
    mode = mode & (~0x0002) # disable line input
    mode = mode & (~0x0004) # disable echo input
    win32.SetConsoleMode(hin, mode)
    stdin = win32api.GetStdHandle(win32api.STD_INPUT_HANDLE)
    handles = [stdin, sock_event]
    try:
        while True:
            i = win32event.WaitForMultipleObjects(handles, 0, 1000)
            if i == win32event.WAIT_TIMEOUT:
                continue
            if handles[i] == stdin:
                buf = ctypes.create_string_buffer(1024)
                bytes_read = ctypes.c_int(0)
                win32.ReadFile(hin, ctypes.byref(buf), 1024, ctypes.byref(bytes_read), None)
                sock.send(buf.value)
            if handles[i] == sock_event:
                data = sock.recv(4096)
                if not data:
                    break
                sys.stdout.write(data)
                win32event.ResetEvent(sock_event)
    finally:
        win32api.CloseHandle(sock_event)
