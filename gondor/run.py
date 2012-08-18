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
    stdin = win32api.GetStdHandle(win32api.STD_INPUT_HANDLE)
    console = win32console.GetStdHandle(win32api.STD_INPUT_HANDLE)
    handles = [stdin, sock_event]
    try:
        while True:
            i = win32event.WaitForMultipleObjects(handles, 0, 1000)
            if i == win32event.WAIT_TIMEOUT:
                continue
            if handles[i] == stdin:
                rs = console.ReadConsoleInput(1)
                if rs[0].EventType == win32console.KEY_EVENT and rs[0].KeyDown:
                    c = rs[0].Char
                    if c == "\x00":
                        continue
                    sock.send(c)
            if handles[i] == sock_event:
                data = sock.recv(4096)
                if not data:
                    break
                sys.stdout.write(data)
                win32event.ResetEvent(sock_event)
    finally:
        win32api.CloseHandle(sock_event)
