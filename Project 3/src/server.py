import base64
import socket
import sys
import threading

# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# connected users: username -> {"control": socket, "data": socket, "key": rsa public key}
# protected by a lock since every client runs in its own thread
# https://docs.python.org/3/library/threading.html#lock-objects
clients = {}
clients_lock = threading.Lock()

# RSA-OAEP padding used for every encrypt/decrypt in this project
OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(), label=None)

# a 2048-bit RSA key can only encrypt 190 bytes at a time with OAEP/SHA256,
# and messages (especially login, which carries a ~450 byte PEM public key)
# can be longer - so plaintext is split into 190-byte chunks, each chunk is
# encrypted into a 256-byte block, and the blocks are concatenated.
ENC_CHUNK = 190   # max plaintext bytes per RSA-2048 OAEP block
DEC_CHUNK = 256   # ciphertext block size produced by RSA-2048

# the server's keypair, created at startup (spec step 2)
server_priv = None
server_pem = None


def encrypt_text(pub_key, text):
    # encrypt text with someone's public key. the binary ciphertext is
    # base64-encoded into a single line so the newline framing from the
    # chat project still works (base64 never contains a newline).
    data = text.encode()
    out = b""
    for i in range(0, len(data), ENC_CHUNK):
        out += pub_key.encrypt(data[i:i + ENC_CHUNK], OAEP)
    return base64.b64encode(out)


def decrypt_line(raw):
    # reverse of encrypt_text using the server's private key.
    # returns the plaintext, or None if the line is not a valid message.
    try:
        data = base64.b64decode(raw, validate=True)
        out = b""
        for i in range(0, len(data), DEC_CHUNK):
            out += server_priv.decrypt(data[i:i + DEC_CHUNK], OAEP)
        return out.decode()
    except Exception:
        return None


def build_message(status, *data_lines):
    # same response format as the chat project:
    # status code, empty line, then the data section if there is one
    msg = status + "\n\n"
    if data_lines:
        msg += "\n".join(data_lines) + "\n"
    return msg


def send_encrypted(sock, pub_key, status, *data_lines):
    # encrypt a response with the recipient's public key and send it as
    # one base64 line. all post-login server -> client traffic uses this.
    if sock is None or pub_key is None:
        return
    try:
        sock.sendall(encrypt_text(pub_key, build_message(status, *data_lines)) + b"\n")
    except OSError:
        pass


def send_plain(sock, status, *data_lines):
    # plaintext send - only used for the connect response (which carries the
    # server's public key, so it cannot be encrypted yet) and for failures
    # before a client key is known
    if sock is None:
        return
    try:
        sock.sendall(build_message(status, *data_lines).encode())
    except OSError:
        pass


def broadcast(status, *data_lines, exclude=None):
    # send one message to every logged in user (except 'exclude'),
    # encrypted with each recipient's own public key
    with clients_lock:
        targets = [(c["data"], c["key"]) for name, c in clients.items()
                   if name != exclude]
    for sock, key in targets:
        send_encrypted(sock, key, status, *data_lines)


def handle_client(control_sock):
    # one thread per client. commands come in on the control socket,
    # responses go out on the data socket (same ftp style as the chat project)
    username = None
    client_key = None
    data_sock = None
    buf = b""
    try:
        while True:
            # read one line. tcp is a byte stream, so buffer until "\n"
            # https://docs.python.org/3/library/socket.html#socket.socket.recv
            while b"\n" not in buf:
                chunk = control_sock.recv(4096)
                if not chunk:      # client disconnected
                    return
                buf += chunk
            raw, buf = buf.split(b"\n", 1)
            raw = raw.strip()
            if not raw:
                continue

            # the connect command is the only plaintext command - everything
            # after it arrives encrypted with the server's public key
            if raw.lower().startswith(b"connect"):
                print("Connection requested. Creating data socket")
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.bind(("", 0))   # port 0 = OS picks a free port
                listener.listen(1)
                data_port = listener.getsockname()[1]
                # response goes back on the control connection and now also
                # carries the server's public key (spec 3a)
                send_plain(control_sock, "200", str(data_port), server_pem.strip())
                data_sock, _ = listener.accept()
                listener.close()
                continue

            # every other command must decrypt with the server's private key
            text = decrypt_line(raw)
            if text is None:
                send_plain(data_sock, "500")
                continue
            print("Received encrypted message")

            plines = text.split("\n")
            parts = plines[0].split(" ")
            cmd = parts[0].lower()

            if cmd == "login":
                # login message format (spec 3b): login \n username \n <public key>
                uname = plines[1].strip() if len(plines) > 1 else ""
                pem = "\n".join(plines[2:]).strip()
                print(f"Login requested by: {uname}")
                key = None
                try:
                    key = serialization.load_pem_public_key(pem.encode())
                except Exception:
                    key = None
                with clients_lock:
                    taken = uname == "" or uname in clients
                    if not taken and key is not None:
                        clients[uname] = {"control": control_sock,
                                          "data": data_sock, "key": key}
                if taken or key is None:
                    # name not unique or a component of the message is missing
                    if key is not None:
                        send_encrypted(data_sock, key, "500")
                    else:
                        send_plain(data_sock, "500")
                else:
                    username = uname
                    client_key = key
                    send_encrypted(data_sock, client_key, "200")
                    # join notification broadcast to the other users
                    broadcast("200", "join", username, exclude=username)

            elif cmd == "who":
                print("Who requested. Sending users.")
                with clients_lock:
                    users = ", ".join(clients)
                send_encrypted(data_sock, client_key, "200", users)

            elif cmd == "broadcast":
                message = plines[0][len("broadcast "):] if len(parts) > 1 else ""
                print(f"Broadcast requested by {username or ''}")
                print(f"Message: {message}")
                # goes to everyone, including the sender, each with their own key
                broadcast("200", "Broadcast", username, message)

            elif cmd == "private":
                recipient = parts[1] if len(parts) > 1 else ""
                message = " ".join(parts[2:])
                print(f"Private message from {username or ''} to {recipient}")
                with clients_lock:
                    target = clients.get(recipient)
                if target is None:
                    send_encrypted(data_sock, client_key, "500")
                else:
                    send_encrypted(target["data"], target["key"],
                                   "200", "Private", username, message)
                    send_encrypted(data_sock, client_key, "200")

            elif cmd == "quit":
                print(f"Quit requested by {username or ''}")
                send_encrypted(data_sock, client_key, "200")
                return

            else:
                send_encrypted(data_sock, client_key, "500")
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
    global server_priv, server_pem
    # sys.argv holds the command line args: https://docs.python.org/3/library/sys.html#sys.argv
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        sys.exit(1)

    print("Starting server...")
    # spec step 2: create an RSA 2048 keypair at startup, kept in memory only
    print("Creating RSA keypair")
    server_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_pem = server_priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    print("RSA keypair created")

    print("Creating server socket")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", int(sys.argv[1])))   # control port from the command line
    server.listen(socket.SOMAXCONN)
    print("Awaiting connections...")

    # one thread per client, same as the chat project
    # https://docs.python.org/3/library/threading.html#threading.Thread
    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
    finally:
        server.close()


if __name__ == "__main__":
    main()