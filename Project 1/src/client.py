import socket
import sys
import threading

# commands waiting for a plain status reply (login/who/private/quit).
# the server's "200" replies all look the same on the wire, so we have to
# remember what we asked for to know what to print
pending = []

# set when the server confirms our quit (or the connection dies) so the
# main input loop knows to stop
# https://docs.python.org/3/library/threading.html#event-objects
quit_event = threading.Event()

# message types the server can push to us because of OTHER users' commands
TYPES = ("Broadcast", "Private", "join", "leave")

def send_cmd(sock, line):
    # commands are single lines ending in "\n"
    # https://docs.python.org/3/library/socket.html#socket.socket.sendall
    try:
        sock.sendall((line + "\n").encode())
    except OSError:
        print("500 status code received.")

def recv_lines(sock):
    # yields one line at a time. tcp is a byte stream, so recv() can return
    # partial or multiple lines - buffer until we have a full one.
    # yield makes this a generator: it pauses here and resumes with buf intact
    # https://docs.python.org/3/reference/expressions.html#yield-expressions
    # https://docs.python.org/3/library/socket.html#socket.socket.recv
    buf = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except OSError:
            return
        if not chunk:        # server closed the connection
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode()

def show_delivery(mtype, lines):
    # messages caused by other users. the first data line says what it is.
    # next(lines, default) pulls one more line out of the generator
    # https://docs.python.org/3/library/functions.html#next
    if mtype == "Broadcast":
        sender = next(lines, "")
        message = next(lines, "")
        print("200 status code received. ")
        print(f"Broadcast message from {sender}: {message}")
    elif mtype == "Private":
        sender = next(lines, "")
        message = next(lines, "")
        print("200 status code received.")
        print(f"{sender}: {message}")
    elif mtype in ("join", "leave"):
        next(lines, "")   # username line, the pdf output shows nothing for these
    else:
        print("200 status code received.")

def handle_message(status, lines):
    if status != "200":
        if pending:
            pending.pop(0)
        print("500 status code received.")
        return

    cmd = pending.pop(0) if pending else None

    if cmd == "login":
        print("200 status code received. Login successful")
    elif cmd == "private":
        print("200 status code received. Message sent.")
    elif cmd == "quit":
        print("200 status code received.")
        quit_event.set()
    elif cmd == "who":
        users = next(lines, "")
        if users in TYPES:
            # a broadcast/private arrived before our who reply, so this
            # message is not ours. handle it and keep waiting for who
            pending.insert(0, "who")
            show_delivery(users, lines)
        else:
            print(f"200 status code received. Users currently connected: {users}")
    else:
        # nothing pending, so this was pushed by another user's command
        show_delivery(next(lines, None), lines)

def reader(sock):
    # runs in the background printing whatever arrives on the data socket.
    # needed because broadcasts/privates can show up at any time while the
    # main thread is stuck in input().
    # message format from the pdf: status line, empty line, data if any
    lines = recv_lines(sock)
    while True:
        status = next(lines, None)
        if status is None:
            break
        if status == "":
            continue
        next(lines, None)            # skip the empty line after the status
        handle_message(status, lines)
    quit_event.set()

def main():
    print("Starting client...")
    control = None
    data = None

    while not quit_event.is_set():
        try:
            # input() blocks for one line of stdin and raises EOFError when
            # stdin closes (e.g. piped input runs out)
            # https://docs.python.org/3/library/functions.html#input
            line = input().strip()
        except EOFError:
            break
        if not line:
            continue
        parts = line.split(" ")
        cmd = parts[0].lower()

        if cmd == "connect":
            if len(parts) != 3:
                print("Usage: connect <ip> <port>")
                continue
            try:
                # connect() is the client side of the tcp handshake
                # https://docs.python.org/3/library/socket.html#socket.socket.connect
                control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                control.connect((parts[1], int(parts[2])))
                send_cmd(control, line)
                # the reply comes back on this same socket:
                # "200\n\n<data port>\n"  (3 newlines total)
                buf = b""
                while buf.count(b"\n") < 3 and not buf.startswith(b"500"):
                    chunk = control.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                reply = buf.decode().split("\n")
            except (OSError, ValueError):
                print("500 status code received.")
                continue
            if reply[0] == "200" and len(reply) >= 3:
                data_port = int(reply[2])
                print(f"200 status code received. Starting data connection on port {data_port}")
                data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data.connect((parts[1], data_port))
                # daemon thread exits automatically with the main program
                # https://docs.python.org/3/library/threading.html#threading.Thread
                threading.Thread(target=reader, args=(data,), daemon=True).start()
            else:
                print("500 status code received.")

        elif cmd in ("login", "who", "broadcast", "private", "quit"):
            if control is None or data is None:
                print("Not connected. Use: connect <ip> <port>")
                continue
            # remember what we asked so the reader knows how to print the
            # reply. broadcast is not tracked because the server answers
            # it with the Broadcast message itself
            if cmd != "broadcast":
                pending.append(cmd)
            send_cmd(control, line)
            if cmd == "quit":
                # give the reader a moment to print the final 200
                quit_event.wait(timeout=5)
                break

        else:
            print("Unknown command")

    for sock in (data, control):
        if sock:
            sock.close()

if __name__ == "__main__":
    main()