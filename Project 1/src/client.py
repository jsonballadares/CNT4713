import socket
import sys
import threading

# ---------------------------------------------------------------------------
# main() / entry point of program
# python reads from top to bottom, so we define main() at the end of the file
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
    server_sock.listen(5)
    print("Awaiting connections...")

    try:
        while True:
            control_sock, addr = server_sock.accept()
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