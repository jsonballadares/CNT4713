import base64
import socket
import threading

# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# commands waiting for a plain status reply (login/who/private/quit).
# the server's "200" replies all look the same, so we have to remember
# what we asked for to know what to print
pending = []

# set when the server confirms our quit (or the connection dies).
# named quit_event rather than quit so it does not shadow the builtin.
# https://docs.python.org/3/library/threading.html#event-objects
quit_event = threading.Event()

# RSA-OAEP padding used for every encrypt/decrypt in this project.
# spec 3c calls for SHA256 in producing the cipher text: OAEP uses SHA256 as
# both the message digest and inside MGF1 mask generation.
OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(), label=None)
ENC_CHUNK = 190   # max plaintext bytes per RSA-2048 OAEP block
DEC_CHUNK = 256   # ciphertext block size produced by RSA-2048

# the client's own keypair, created at startup (spec client step 1) and the
# server's public key, learned from the connect response (spec client step 3b)
priv_key = None
pub_pem = None
server_key = None

# spec client steps 4-6: login must succeed before any other command, because
# the server cannot encrypt a reply until it has stored our public key
logged_in = False


def encrypt_text(pub_key, text):
    # encrypt with a public key, chunked because RSA can only encrypt 190
    # bytes at a time. base64 turns the binary ciphertext into one line so
    # the chat project's newline framing still works.
    data = text.encode()
    out = b""
    for i in range(0, len(data), ENC_CHUNK):
        out += pub_key.encrypt(data[i:i + ENC_CHUNK], OAEP)
    return base64.b64encode(out)


def decrypt_line(raw):
    # decrypt one base64 line with our private key, or None if invalid
    try:
        data = base64.b64decode(raw, validate=True)
        out = b""
        for i in range(0, len(data), DEC_CHUNK):
            out += priv_key.decrypt(data[i:i + DEC_CHUNK], OAEP)
        return out.decode()
    except Exception:
        return None


def send_encrypted(sock, text):
    # spec client step 6a: build the message, encrypt it with the SERVER's
    # public key, and send it on the control connection as one base64 line
    try:
        sock.sendall(encrypt_text(server_key, text) + b"\n")
    except OSError:
        print("500 status code received.")


def recv_lines(sock):
    # yields one line at a time. tcp is a byte stream, so recv() can return
    # partial or multiple lines - buffer until we have a full one
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
            yield line


def handle_message(text):
    # each decrypted message is the full chat-project format:
    # status line, empty line, data section if any
    lines = text.split("\n")
    status = lines[0].strip()
    data = lines[2:] if len(lines) >= 3 else []

    # join/leave notices: the pdf output shows nothing for these at all
    if data and data[0] in ("join", "leave"):
        return

    # per the pdf template, every displayed response is announced first
    print("Received encrypted message")

    if status != "200":
        if pending:
            pending.pop(0)
        print("500 status code received.")
        return

    # deliveries caused by other users announce their type in the data
    if data and data[0] == "Broadcast":
        sender = data[1] if len(data) > 1 else ""
        message = data[2] if len(data) > 2 else ""
        print("200 status code received. ")
        print(f"Broadcast message from {sender}: {message}")
        return
    if data and data[0] == "Private":
        sender = data[1] if len(data) > 1 else ""
        message = data[2] if len(data) > 2 else ""
        print("200 status code received.")
        print(f"{sender}: {message}")
        return

    # otherwise this is the reply to our own last command
    cmd = pending.pop(0) if pending else None
    if cmd == "login":
        global logged_in
        logged_in = True
        print("200 status code received. Login successful")
    elif cmd == "private":
        print("200 status code received. Message sent.")
    elif cmd == "quit":
        print("200 status code received.")
        quit_event.set()
    elif cmd == "who":
        users = data[0] if data else ""
        print(f"200 status code received. Users currently connected: {users}")
    else:
        print("200 status code received.")


def reader(sock):
    # background thread: decrypt and display whatever arrives on the data
    # socket. needed because broadcasts/privates can show up at any time
    # while the main thread is stuck in input().
    for raw in recv_lines(sock):
        text = decrypt_line(raw.strip())
        if text is not None:
            handle_message(text)
    quit_event.set()


def main():
    global priv_key, pub_pem, server_key
    print("Starting client...")
    # spec client step 1: create our own keypair at startup, in memory only
    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    control = None
    data = None

    while not quit_event.is_set():
        try:
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
            try:
                # https://docs.python.org/3/library/socket.html#socket.socket.connect
                control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                control.connect((parts[1], int(parts[2])))
                control.sendall((line + "\n").encode())
                # spec client step 3: the reply is plaintext (it is what
                # delivers the server's key) - "200\n\n<data port>\n<key>\n"
                # the PEM key spans multiple lines, so read until its
                # END PUBLIC KEY footer arrives (spec client step 3)
                buf = b""
                while b"-----END PUBLIC KEY-----" not in buf:
                    chunk = control.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                reply = buf.decode().split("\n")
            except (OSError, ValueError):
                print("500 status code received.")
                continue
            if reply[0].strip() == "200" and len(reply) >= 4:
                data_port = int(reply[2].strip())
                # everything from the port line onward that looks like PEM
                pem = "\n".join(reply[3:]).strip()
                server_key = serialization.load_pem_public_key(pem.encode())
                print(f"200 status code received. Starting data connection on port {data_port}")
                data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data.connect((parts[1], data_port))
                threading.Thread(target=reader, args=(data,), daemon=True).start()
            else:
                print("500 status code received.")

        elif cmd in ("login", "who", "broadcast", "private", "quit"):
            if control is None or data is None or server_key is None:
                print("Not connected. Use: connect <ip> <port>")
                continue
            if cmd != "login" and not logged_in:
                # without a successful login the server has no key to encrypt
                # a reply with, so the command would never be answered
                print("Not logged in. Use: login <username>")
                continue
            if cmd == "login":
                # spec client step 4: send the username AND our public key,
                # all encrypted with the server's public key:
                #     login / <username> / <public key>
                uname = parts[1] if len(parts) > 1 else ""
                payload = f"login\n{uname}\n{pub_pem}"
            else:
                payload = line
            # remember what we asked so the reader knows how to print the
            # reply. broadcast is not tracked because the server answers it
            # with the Broadcast message itself
            if cmd != "broadcast":
                pending.append(cmd)
            send_encrypted(control, payload)
            if cmd == "quit":
                quit_event.wait(timeout=5)
                break

        else:
            print("Unknown command")

    for sock in (data, control):
        if sock:
            sock.close()


if __name__ == "__main__":
    main()