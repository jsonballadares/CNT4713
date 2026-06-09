import socket
import sys
import threading

# ---------------------------------------------------------------------------
# clients serves as our shared memory amongs threads
# dictionaries are not thread safe by default in python
# https://docs.python.org/3/library/threadsafety.html
# ---------------------------------------------------------------------------
clients = {}                       # username -> {"control": socket, "data": socket} at runtime our dict should looke like so
clients_lock = threading.Lock()    # this is a mutex. protects the dict across threads without this we can run into memory corruption unexpected behavior race conditions etc.

# ---------------------------------------------------------------------------
# b"\x00" is the literarl represenation of a null byte utilized as a DELIMITER we define for TCP to indicate the end of a message. 
# this is necessary because TCP is a stream-oriented protocol, and does not preserve message boundaries. 
# TCP guarantees that data will be delivered in order and without duplication, but it does not guarantee that messages will be delivered in the
# same chunks as they were sent. By using a DELIMITER, we can ensure that the receiver can correctly parse the incoming data into discrete messages this is called framing.
# https://medium.com/@yashvaishnav1404/message-framing-in-tcp-sockets-b3859302de4e
# ---------------------------------------------------------------------------
MSG_DELIMITER = b"\x00"   # server -> client: messages are multi-line, NUL-framed
CMD_DELIMITER = b"\n"     # client -> server: commands are single-line, newline-framed
MAX_RECV_BYTES = 4096.    # MAX_RECV_BYTES is the maximum number of bytes copied out of the kernel's TCP receive buffer per recv() call.

# ---------------------------------------------------------------------------
# send_message() is a helper function that takes a socket that wraps around sock.sendall() 
# appends the DELIMITER to the message, encodes it as UTF-8 bytes, 
# and sends it over the socket using sendall(). so we move from application layer -> transport layer!
# https://realpython.com/python-sockets/
# ---------------------------------------------------------------------------
def send_message(sock, text):
    try:
        sock.sendall(text.encode("utf-8") + MSG_DELIMITER)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# recv_commands() is a helper function that takes a socket that wraps around sock.recv()
# it continuously reads data from the socket, buffering it until it encounters a newline character (\n).
# once a complete line is received, it decodes the bytes to a UTF-8 string, strips any leading or trailing whitespace, 
# and yields the command line for further processing. the replace argument in decode() is used to handle any decoding errors 
# gracefully by replacing invalid byte sequences with a placeholder character, 
# ensuring that the server can continue processing commands without crashing due to encoding issues.
# https://realpython.com/python-sockets/
# ---------------------------------------------------------------------------
def recv_commands(sock):
    buf = b""
    while True:
        try:
            chunk = sock.recv(MAX_RECV_BYTES)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while CMD_DELIMITER in buf:
            line, buf = buf.split(CMD_DELIMITER, 1)
            yield line.decode("utf-8", "replace").strip()

# ---------------------------------------------------------------------------
# recv_commands() is a helper function that takes a text message and an optional exclude username,
# it iterates through the clients dictionary, sending the message to all connected clients except the one specified in the exclude parameter. 
# this is used for broadcasting messages to all clients except the sender, such as when a user joins or leaves the chat, or 
# when a user sends a broadcast message. the clients_lock is used to ensure thread safety when accessing the shared clients dictionary across multiple threads.
# ---------------------------------------------------------------------------
def broadcast_msg(text, exclude=None):
    with clients_lock:
        targets = [info["data"] for user, info in clients.items() if user != exclude]
    for sock in targets:
        send_message(sock, text)

# ---------------------------------------------------------------------------
# each thread will run the client_thread() function, which is responsible for 
# managing the communication with a single client using FTP style control 
# and data sockets. control was established in main() and data is established in client_thread()
# this function also will handle the clients commands defined in the PDF and 
# send appropriate responses back to the client.
# https://docs.python.org/3/howto/sockets.html
# ---------------------------------------------------------------------------
def client_thread(control_sock, addr):
    username = None
    data_sock = None
    try:
        for line in recv_commands(control_sock):
            if not line:
                continue
            parts = line.split(" ")
            cmd = parts[0].lower()

            match cmd:
                # ---- connect <ip> <port> ----
                case "connect":
                    print("Connection requested. Creating data socket")
                    data_listener = socket.socket(socket.AF_INET,
                                                  socket.SOCK_STREAM)
                    data_listener.setsockopt(socket.SOL_SOCKET,
                                             socket.SO_REUSEADDR, 1)
                    data_listener.bind(("", 0))  # OS picks a free DATA PORT
                    data_listener.listen(1)
                    data_port = data_listener.getsockname()[1]
                    # Response to connect goes back on the control connection
                    send_message(control_sock, "200\n\n{}".format(data_port))
                    data_sock, _ = data_listener.accept()
                    data_listener.close()

                # ---- login <username> ----
                case "login":
                    uname = parts[1] if len(parts) > 1 else ""
                    print("Login requested by: {}".format(uname))
                    if data_sock is None:
                        continue
                    with clients_lock:
                        taken = (not uname) or (uname in clients)
                    if taken:
                        send_message(data_sock, "500")
                        continue
                    username = uname
                    with clients_lock:
                        clients[username] = {"control": control_sock,
                                             "data": data_sock}
                    send_message(data_sock, "200")
                    # Join notification broadcast to the other users
                    broadcast_msg("200\n\njoin\n{}".format(username),
                                  exclude=username)

                # ---- who ----
                case "who":
                    print("Who requested. Sending users.")
                    with clients_lock:
                        users = ", ".join(clients.keys())
                    send_message(data_sock, "200\n\n{}".format(users))

                # ---- broadcast <message> ----
                case "broadcast":
                    message = line[len("broadcast "):] if len(parts) > 1 else ""
                    print("Broadcast requested by {}".format(username))
                    print("Message: {}".format(message))
                    broadcast_msg("200\n\nBroadcast\n{}\n{}".format(username,
                                                                    message))

                # ---- private <username> <message> ----
                case "private":
                    recipient = parts[1] if len(parts) > 1 else ""
                    message = " ".join(parts[2:]) if len(parts) > 2 else ""
                    print("Private message from {} to {}".format(username,
                                                                 recipient))
                    with clients_lock:
                        target = clients.get(recipient)
                    if target is None:
                        send_message(data_sock, "500")
                    else:
                        send_message(target["data"],
                                 "200\n\nPrivate\n{}\n{}".format(username,
                                                                 message))
                        send_message(data_sock, "200")

                # ---- quit ----
                case "quit":
                    print("Quit requested by {}".format(username))
                    if data_sock is not None:
                        send_message(data_sock, "200")
                    break

                # ---- unknown command ----
                case _:
                    if data_sock is not None:
                        send_message(data_sock, "500")
    finally:
        # Remove from active list, notify remaining users, close sockets
        if username is not None:
            with clients_lock:
                clients.pop(username, None)
            broadcast_msg("200\n\nleave\n{}".format(username))
        try:
            control_sock.close()
        except OSError:
            pass
        if data_sock is not None:
            try:
                data_sock.close()
            except OSError:
                pass
        


# ---------------------------------------------------------------------------
# main() / entry point of program
# python reads from top to bottom, so we define main() at the end of the file
# main() reads the port supplied by the user via CLI, creates a listening socket, 
# and waits for incoming connections. For each accepted connection, 
# it spawns a new thread to handle the client's requests concurrently.
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 2:
        # the server will be started via command line with a user provided TCP port. This will be called the CONTROL PORT.
        # a dedicated communication channel used exclusively for sending administrative commands, configuration data, or state signals, 
        # completely separated from the primary data streams. this design pattern was made famous by FTP.
        print("Usage: python server.py <control_port>")
        sys.exit(1)
    control_port = int(sys.argv[1]) # this gets us the control_port from user via python server.py 8991

    # https://docs.python.org/3/howto/sockets.html#sockets
    # the server will listen for incoming connections on the specified CONTROL PORT, and for each accepted connection
    # it will spawn a new thread to handle the client's requests concurrently.
    print("Starting server...")
    print("Creating server socket")
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("", control_port)) # "" arg means accept connections from any network interface on the host machine, rather than restricting it to a specific IP or hardcoding localhost. this is basically (0.0.0.0).
    server_sock.listen(socket.SOMAXCONN) # handle as many pending connections as the system allows this really only matters when bursts of incoming connections come in. this prevents the server from being overwhelmed by too many simultaneous connection attempts.
    print("Awaiting connections...")

    try:
        while True:
            # accept() this is a blocking call that waits until a client connects to the server. 
            # which is why we spawn a new thread for each client, so that the server can continue 
            # accepting new connections while existing clients are being handled.
            control_sock, addr = server_sock.accept() 
            # daemon option is used to ensure that the thread will automatically exit when the main program terminates
            # preventing any potential resource leaks or hanging threads. this is just graceful termination.
            t = threading.Thread(target=client_thread,
                                 args=(control_sock, addr),
                                 daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
    finally:
        # this is the main loop of the server it will run indefinitely until the server is manually stopped (i.e. Ctrl+C) or by an unhandled exception. when the server is stopped, it will close the listening socket and exit gracefully as the finally block guareentees us.
        server_sock.close()

# ---------------------------------------------------------------------------
# this if statement ensures that main() is only called when this script is run directly,
# and not when it is imported as a module in another script.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()