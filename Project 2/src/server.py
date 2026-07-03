import os
import socket
import sys
import threading

# connected users: username -> {"control": socket, "data": socket}
# protected by a lock since every client runs in its own thread
# https://docs.python.org/3/library/threading.html#lock-objects
clients = {}
clients_lock = threading.Lock()

# all stored files live in one shared directory next to the server.
# created at startup if it does not already exist.
FILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_files")


def send_msg(sock, status, *data):
    # text responses follow the format from the pdf:
    # status code, empty line, then the data section if there is one.
    # the trailing newline marks the end of the message (tcp is a byte
    # stream, it doesn't keep message boundaries for us)
    if sock is None:
        return
    msg = status + "\n\n"
    if data:
        msg += "\n".join(data) + "\n"
    try:
        # sendall keeps sending until everything is handed to tcp
        # https://docs.python.org/3/library/socket.html#socket.socket.sendall
        sock.sendall(msg.encode())
    except OSError:
        pass


def open_file_port():
    # open a brand new listening socket for a single file transfer and return
    # (listener, port). per FTP, each stor/retr uses its own data connection
    # whose close signals end-of-file - so binary file data needs no framing.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("", 0))   # port 0 = OS picks a free port
    listener.listen(1)
    return listener, listener.getsockname()[1]


def handle_client(control_sock):
    # one thread per client. commands come in on the control socket,
    # text responses go out on the data socket (ftp style, like the pdf says).
    # file contents move over their own short-lived connections.
    username = None
    data_sock = None
    buf = b""
    try:
        while True:
            # read one command line. recv() can return partial or multiple
            # commands, so buffer until we have a full line ending in "\n"
            # https://docs.python.org/3/library/socket.html#socket.socket.recv
            while b"\n" not in buf:
                chunk = control_sock.recv(4096)
                if not chunk:
                    # client disconnected (recv returning 0 bytes means the
                    # peer closed the connection, see
                    # https://docs.python.org/3/howto/sockets.html#using-a-socket)
                    return
                buf += chunk
            line, buf = buf.split(b"\n", 1)
            line = line.decode().strip()
            if not line:
                continue
            parts = line.split(" ")
            cmd = parts[0].lower()

            if cmd == "connect":
                print("Connection requested. Creating data socket")
                listener, data_port = open_file_port()
                # per the pdf the connect response goes back on the
                # control connection, everything else uses the data port
                send_msg(control_sock, "200", str(data_port))
                data_sock, _ = listener.accept()
                listener.close()

            elif cmd == "login":
                uname = parts[1] if len(parts) > 1 else ""
                print(f"Login requested by: {uname}")
                with clients_lock:
                    taken = uname == "" or uname in clients
                    if not taken:
                        clients[uname] = {"control": control_sock,
                                          "data": data_sock}
                if taken:
                    # username must be unique
                    send_msg(data_sock, "500")
                else:
                    username = uname
                    send_msg(data_sock, "200")

            elif cmd == "list":
                print(f"List requested by {username or ''}. Sending files.")
                try:
                    files = sorted(os.listdir(FILE_DIR))
                except OSError:
                    files = []
                send_msg(data_sock, "200", ", ".join(files))

            elif cmd == "stor":
                # client wants to upload a file. server opens a fresh data
                # connection, reads bytes until the client closes it (EOF),
                # writes them to disk, then replies 200 on the control data sock.
                filename = parts[1] if len(parts) > 1 else ""
                print(f"Stor {filename} requested by {username or ''}")
                listener, file_port = open_file_port()
                # tell the client which port to send the file contents to
                send_msg(data_sock, "200", str(file_port))
                conn, _ = listener.accept()
                listener.close()
                try:
                    path = os.path.join(FILE_DIR, os.path.basename(filename))
                    with open(path, "wb") as f:
                        while True:
                            chunk = conn.recv(4096)
                            if not chunk:      # client closed = whole file received
                                break
                            f.write(chunk)
                    conn.close()
                    print("STOR complete")
                    send_msg(data_sock, "200")
                except OSError:
                    conn.close()
                    send_msg(data_sock, "500")

            elif cmd == "retr":
                # client wants to download a file. server opens a fresh data
                # connection, streams the file, then closes it (close = EOF).
                filename = parts[1] if len(parts) > 1 else ""
                path = os.path.join(FILE_DIR, os.path.basename(filename))
                if not os.path.isfile(path):
                    # file does not exist - only the failing status, no port
                    print(f"Retr requested by {username or ''}. File not found: {filename}")
                    send_msg(data_sock, "500")
                else:
                    print(f"Retr requested by {username or ''}. Sending file: {filename}")
                    listener, file_port = open_file_port()
                    # tell the client which port to receive the file contents on
                    send_msg(data_sock, "200", str(file_port))
                    conn, _ = listener.accept()
                    listener.close()
                    try:
                        with open(path, "rb") as f:
                            while True:
                                chunk = f.read(4096)
                                if not chunk:
                                    break
                                conn.sendall(chunk)
                        print("File sent.")
                    except OSError:
                        pass
                    conn.close()   # closing the connection signals end-of-file

            elif cmd == "dele":
                filename = parts[1] if len(parts) > 1 else ""
                print(f"Dele requested by {username or ''}. Deleting file: {filename}")
                path = os.path.join(FILE_DIR, os.path.basename(filename))
                try:
                    os.remove(path)
                    print("Delete complete")
                    send_msg(data_sock, "200")
                except OSError:
                    # file did not exist or could not be removed
                    send_msg(data_sock, "500")

            elif cmd == "quit":
                print(f"Quit requested by {username or ''}")
                send_msg(data_sock, "200")
                return

            else:
                send_msg(data_sock, "500")
    finally:
        # always clean up: remove the user, close sockets
        if username:
            with clients_lock:
                clients.pop(username, None)
        control_sock.close()
        if data_sock:
            data_sock.close()


def main():
    # sys.argv holds the command line args: https://docs.python.org/3/library/sys.html#sys.argv
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        sys.exit(1)

    # make sure the shared file directory exists
    os.makedirs(FILE_DIR, exist_ok=True)

    print("Starting server...")
    print("Creating server socket")
    # AF_INET = ipv4, SOCK_STREAM = tcp
    # https://docs.python.org/3/library/socket.html#socket.socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # lets us restart the server right away without "address already in use"
    # https://docs.python.org/3/library/socket.html#socket.socket.setsockopt
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", int(sys.argv[1])))   # control port from the command line
    server.listen(socket.SOMAXCONN)
    print("Awaiting connections...")

    # accept() blocks until someone connects and returns a NEW socket for that
    # client, so each client gets its own thread and the loop keeps accepting
    # https://docs.python.org/3/library/socket.html#socket.socket.accept
    # daemon threads exit automatically when the main program does
    # https://docs.python.org/3/library/threading.html#threading.Thread
    try:
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        # ctrl+c lands here instead of printing a traceback
        print("\nServer shutting down.")
    finally:
        server.close()


if __name__ == "__main__":
    main()