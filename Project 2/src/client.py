import os
import socket

def send_cmd(sock, line):
    # commands are single lines ending in "\n"
    # https://docs.python.org/3/library/socket.html#socket.socket.sendall
    try:
        sock.sendall((line + "\n").encode())
        return True
    except OSError:
        print("500 status code received.")
        return False


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


def read_status(lines):
    # every text response starts "status \n <empty line>", so consume both
    # and hand back the status. data lines (if any) are read by the caller.
    status = next(lines, None)
    if status is None:
        return None          # connection closed
    next(lines, None)        # the <EMPTY LINE> from the message format
    return status.strip()


def stor(ip, port, filename):
    # connect to the file port the server gave us, stream the file, then
    # close the connection. closing tells the server the file is complete.
    # https://www.cs.colostate.edu/helpdocs/ftp.html
    # https://medium.com/@CHICHEEE/build-a-simple-file-transfer-system-using-python-network-programming-project-c9962cf238c0
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
    # https://www.cs.colostate.edu/helpdocs/ftp.html
    # https://medium.com/@CHICHEEE/build-a-simple-file-transfer-system-using-python-network-programming-project-c9962cf238c0
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


def main():
    print("Starting client...")
    control = None
    data = None
    lines = None         # line buffer over the persistent data connection
    server_ip = None

    while True:
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
                lines = recv_lines(data)
            else:
                print("500 status code received.")

        elif cmd in ("login", "list", "stor", "retr", "dele", "quit"):
            if control is None or data is None:
                print("Not connected. Use: connect <ip> <port>")
                continue

            if cmd == "login":
                if not send_cmd(control, line):
                    continue
                status = read_status(lines)
                if status == "200":
                    print("200 status code received. Login successful")
                else:
                    print("500 status code received.")

            elif cmd == "list":
                if not send_cmd(control, line):
                    continue
                status = read_status(lines)
                if status == "200":
                    files = next(lines, "")
                    print(f"200 status code received. Files: {files}")
                else:
                    print("500 status code received.")

            elif cmd == "stor":
                filename = parts[1] if len(parts) > 1 else ""
                # the file to upload must exist locally before we ask
                if not os.path.isfile(filename):
                    print("500 status code received.")
                    continue
                if not send_cmd(control, line):
                    continue
                status = read_status(lines)
                if status != "200":
                    print("500 status code received.")
                    continue
                # server handed us the port for the one-off file connection
                port = int(next(lines, "0"))
                if not stor(server_ip, port, filename):
                    print("500 status code received.")
                    continue
                # server confirms once it has received the whole file
                status = read_status(lines)
                if status == "200":
                    print("200 status code received. File Sent.")
                else:
                    print("500 status code received.")

            elif cmd == "retr":
                filename = parts[1] if len(parts) > 1 else ""
                if not send_cmd(control, line):
                    continue
                status = read_status(lines)
                if status != "200":
                    # file does not exist on the server
                    print("500 status code received.")
                    continue
                port = int(next(lines, "0"))
                # no status follows a successful transfer - the file
                # connection closing IS the end-of-file signal, so this
                # line is printed by us, not echoed from the server
                if retr(server_ip, port, filename):
                    print("File retrieved.")
                else:
                    print("500 status code received.")

            elif cmd == "dele":
                if not send_cmd(control, line):
                    continue
                status = read_status(lines)
                if status == "200":
                    print("200 status code received. File deleted.")
                else:
                    print("500 status code received.")

            elif cmd == "quit":
                if send_cmd(control, line):
                    status = read_status(lines)
                    if status == "200":
                        print("200 status code received.")
                break

        else:
            print("Unknown command")

    for sock in (data, control):
        if sock:
            try:
                sock.close()
            except OSError:
                pass


if __name__ == "__main__":
    main()