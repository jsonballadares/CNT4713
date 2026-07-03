import os
import socket
import threading

# commands waiting for a plain status reply (login/dele/quit).
# the server's "200" replies all look the same on the wire, so we have to
# remember what we asked for to know what to print
pending = []

# set when the server confirms our quit (or the connection dies) so the
# main input loop knows to stop
# https://docs.python.org/3/library/threading.html#event-objects
quit = threading.Event()

# stor/retr need to act on the response (open a file connection) on the
# reader thread, so the main thread hands the pending filename across here
transfer = {}


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


def stor(ip, port, filename):
    # connect to the file port the server gave us, stream the file, then
    # close the connection. closing tells the server the file is complete.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                s.sendall(chunk)
        s.close()   # close = end of file
        return True
    except OSError:
        return False


def retr(ip, port, filename):
    # connect to the file port the server gave us and read bytes until the
    # server closes the connection (close = end of file), saving to disk.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        with open(filename, "wb") as f:
            while True:
                chunk = s.recv(4096)
                if not chunk:   # server closed = whole file received
                    break
                f.write(chunk)
        s.close()
        return True
    except OSError:
        return False


def handle_message(status, lines, server_ip):
    if status != "200":
        cmd = pending.pop(0) if pending else None
        print("500 status code received.")
        return

    cmd = pending.pop(0) if pending else None

    if cmd == "login":
        print("200 status code received. Login successful")
    elif cmd == "dele":
        print("200 status code received. File deleted.")
    elif cmd == "quit":
        print("200 status code received.")
        quit.set()
    elif cmd == "list":
        files = next(lines, "")
        print(f"200 status code received. Files: {files}")
    elif cmd == "stor":
        # server replied with the file port; stream the file up to it
        port = int(next(lines, "0"))
        filename = transfer.get("stor", "")
        if stor(server_ip, port, filename):
            # the server sends a second 200 once it has the whole file
            pending.insert(0, "stor_done")
        else:
            print("500 status code received.")
    elif cmd == "stor_done":
        print("200 status code received. File Sent.")
    elif cmd == "retr":
        # server replied with the file port; download the file from it
        port = int(next(lines, "0"))
        filename = transfer.get("retr", "")
        if retr(server_ip, port, filename):
            print("File retrieved.")
        else:
            print("500 status code received.")
    else:
        print("200 status code received.")


def reader(sock, server_ip):
    # runs in the background reading the persistent data connection.
    # message format from the pdf: status line, empty line, data if any
    lines = recv_lines(sock)
    while True:
        status = next(lines, None)
        if status is None:
            break
        if status == "":
            continue
        next(lines, None)            # skip the empty line after the status
        handle_message(status.strip(), lines, server_ip)
    quit.set()


def main():
    print("Starting client...")
    control = None
    data = None
    server_ip = None

    while not quit.is_set():
        try:
            # input() blocks for one line of stdin and raises EOFError when
            # stdin closes (e.g. piped input runs out)
            # https://docs.python.org/3/library/functions.html#input
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("Server socket closed.")
            break
        if not line:
            continue
        parts = line.split(" ")
        cmd = parts[0].lower()

        if cmd == "connect":
            if len(parts) != 3:
                print("Usage: connect <ip> <port>")
                continue
            server_ip = parts[1]
            try:
                # connect() is the client side of the tcp handshake
                # https://docs.python.org/3/library/socket.html#socket.socket.connect
                control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                control.connect((server_ip, int(parts[2])))
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
                data.connect((server_ip, data_port))
                # daemon thread exits automatically with the main program
                # https://docs.python.org/3/library/threading.html#threading.Thread
                threading.Thread(target=reader, args=(data, server_ip), daemon=True).start()
            else:
                print("500 status code received.")

        elif cmd in ("login", "list", "stor", "retr", "dele", "quit"):
            if control is None or data is None:
                print("Not connected. Use: connect <ip> <port>")
                continue
            # stor/retr need a local filename present before we send, and the
            # reader thread needs to know it to open the file connection
            if cmd in ("stor", "retr"):
                filename = parts[1] if len(parts) > 1 else ""
                if cmd == "stor" and not os.path.isfile(filename):
                    print("500 status code received.")
                    continue
                transfer[cmd] = filename
            # remember what we asked so the reader knows how to print the reply
            pending.append(cmd)
            send_cmd(control, line)
            if cmd == "quit":
                quit.wait(timeout=5)
                break

        else:
            print("Unknown command")

    for sock in (data, control):
        if sock:
            sock.close()


if __name__ == "__main__":
    main()