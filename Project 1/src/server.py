import socket
import sys
import threading

# connected users: username -> {"control": socket, "data": socket}
# protected by a lock since every client runs in its own thread
# https://docs.python.org/3/library/threading.html#lock-objects
clients = {}
clients_lock = threading.Lock()

def send_msg(sock, status, *data):
    # responses follow the format from the pdf:
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

def broadcast(status, *data, exclude=None):
    # send one message to every logged in user (except 'exclude')
    with clients_lock:
        socks = [c["data"] for name, c in clients.items() if name != exclude]
    for s in socks:
        send_msg(s, status, *data)

def handle_client(control_sock):
    # one thread per client. commands come in on the control socket,
    # responses go out on the data socket (ftp style, like the pdf says)
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
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.bind(("", 0))   # port 0 = OS picks a free port
                listener.listen(1)
                data_port = listener.getsockname()[1]
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
                    # let everyone else know this user joined
                    broadcast("200", "join", username, exclude=username)

            elif cmd == "who":
                print("Who requested. Sending users.")
                with clients_lock:
                    users = ", ".join(clients)
                send_msg(data_sock, "200", users)

            elif cmd == "broadcast":
                message = line[len("broadcast "):] if len(parts) > 1 else ""
                print(f"Broadcast requested by {username or ''}")
                print(f"Message: {message}")
                # goes to everyone, including the sender
                broadcast("200", "Broadcast", username, message)

            elif cmd == "private":
                recipient = parts[1] if len(parts) > 1 else ""
                message = " ".join(parts[2:])
                print(f"Private message from {username or ''} to {recipient}")
                with clients_lock:
                    target = clients.get(recipient)
                if target is None:
                    # recipient does not exist
                    send_msg(data_sock, "500")
                else:
                    send_msg(target["data"], "200", "Private",
                             username, message)
                    send_msg(data_sock, "200")

            elif cmd == "quit":
                print(f"Quit requested by {username or ''}")
                send_msg(data_sock, "200")
                return

            else:
                send_msg(data_sock, "500")
    finally:
        # always clean up: remove the user, tell the others, close sockets
        if username:
            with clients_lock:
                clients.pop(username, None)
            broadcast("200", "leave", username)
        control_sock.close()
        if data_sock:
            data_sock.close()

def main():
    # sys.argv holds the command line args: https://docs.python.org/3/library/sys.html#sys.argv
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        sys.exit(1)

    print("Starting server...")
    print("Creating server socket")
    # AF_INET = ipv4, SOCK_STREAM = tcp
    # https://docs.python.org/3/library/socket.html#socket.socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # lets us restart the server right away without "address already in use"
    # https://docs.python.org/3/library/socket.html#socket.socket.setsockopt
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", int(sys.argv[1])))   # control port from the command line
    server.listen(5)
    print("Awaiting connections...")

    # accept() blocks until someone connects and returns a NEW socket for that
    # client, so each client gets its own thread and the loop keeps accepting
    # https://docs.python.org/3/library/socket.html#socket.socket.accept
    # daemon threads exit automatically when the main program does
    # https://docs.python.org/3/library/threading.html#threading.Thread
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    main()