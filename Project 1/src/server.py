import socket
import sys
import threading

# ---------------------------------------------------------------------------
# TERM is a null character utilized as a deliminator we define for TCP to indicate the end of a message. this is necessary because TCP is a stream-oriented protocol, and does
# not preserve message boundaries. TCP guarantees that data will be delivered in order and without duplication, but it does not guarantee that messages will be delivered in the
# same chunks as they were sent. By using a deliminator, we can ensure that the receiver can correctly parse the incoming data into discrete messages this is called framing.
# ---------------------------------------------------------------------------
TERM = "\0" 

# ---------------------------------------------------------------------------
# send_message() is a helper function that takes a socket and a text message as arguments, appends the TERM deliminator to the message, encodes it as UTF-8 bytes, and sends it over the socket using sendall().

# text + TERM is the "framing" mechanism

# TCP is a byte stream protocol, which means that we must convert/encode our human readable text into computer readable bytes before sending them over the network. UTF-8 is a common encoding that can represent all Unicode characters not just ASCII, if we used just ASCII we would run into edge cases in other languages etc.
# ---------------------------------------------------------------------------
def send_message(sock, text):
    try:
        sock.sendall((text + TERM).encode("utf-8"))
        return True
    except OSError:
        return False

# ---------------------------------------------------------------------------
# each thread will run the handle_client() function, which is responsible for 
# managing the communication with a single client using FTP style control 
# and data sockets. 
# control was established in main() and data is established in handle_client()
# ---------------------------------------------------------------------------
def handle_client(control_sock, addr, host):
    print("Connection requested. Creating data socket")

    # https://docs.python.org/3/howto/sockets.html#sockets
    # creating the data socket using an ephemeral port (port 0)
    data_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    data_listener.bind((host, 0)) # kernel picks a random free port
    data_listener.listen(1) # data socket will only accept one connection
    data_port = data_listener.getsockname()[1] # at runtime we are unaware of the port number assigned to the data socket by the kernel, so we retrieve it using getsockname().

    # we are now able to provide that port number to the client over the control connection, so that the client can establish a data connection.
    send_message(control_sock, response(200, str(data_port)))

    # 3) Wait for the client to open its DATA connection to that port.
    data_listener.settimeout(15)
    try:
        data_sock, _ = data_listener.accept()
    except (socket.timeout, OSError):
        control_sock.close()
        data_listener.close()
        return
    finally:
        data_listener.close()              # only one data connection per client

    conn = ClientConn(control_sock, data_sock, addr)
    reader = MessageReader(control_sock)

    # 4) Service commands until the client quits or disconnects.
    try:
        while True:
            msg = reader.read_message()
            if msg is None:
                break
            if process_command(conn, msg) == "quit":
                break
    finally:
        cleanup_client(conn)

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
    try:
        control_port = int(sys.argv[1])
    except ValueError:
        print("CONTROL PORT must be an integer.")
        sys.exit(1)
    
    
    # allow the server to accept connections from any network interface on the host machine, rather than restricting it to a specific IP 
    host = "" # this is basically (0.0.0.0)              

    # https://docs.python.org/3/howto/sockets.html#sockets
    # the server will listen for incoming connections on the specified CONTROL PORT, and for each accepted connection
    # it will spawn a new thread to handle the client's requests concurrently.
    print("Starting server...")
    print("Creating server socket")
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, control_port))
    server_sock.listen(socket.SOMAXCONN) # handle as many pending connections as the system allows this really only matters 
    # when bursts of incoming connections come in. this prevents the server from being overwhelmed by too many simultaneous connection attempts.
    print("Awaiting connections...")

    try:
        while True:
            # accept() this is a blocking call that waits until a client connects to the server. 
            # which is why we spawn a new thread for each client, so that the server can continue 
            # accepting new connections while existing clients are being handled.
            control_sock, addr = server_sock.accept() 
            # daemon option is used to ensure that the thread will automatically exit when the main program terminates
            # preventing any potential resource leaks or hanging threads.
            t = threading.Thread(target=handle_client,
                                 args=(control_sock, addr, host),
                                 daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
    finally:
        server_sock.close()

# ---------------------------------------------------------------------------
# this if statement ensures that main() is only called when this script is run directly,
# and not when it is imported as a module in another script.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()