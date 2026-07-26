CNT4713 - Project 3 - Chat Cryptography Project
===============================================

Group Members
-------------
Jason Balladares - 5760817

Mahadi Rahman - 6406575

Phoenix Depaz - 6234251

Notes
-----
here is where we have the source code hosted w/more instructions: https://github.com/jsonballadares/CNT4713/tree/main/Project%203
per the instructions on cavnas we will submit only the client.py server.py answers.txt and readme.txt
and provide the url to our demo video here w/wireshark commentary: https://drive.google.com/file/d/1FmC-lm86cwyAwINFpyt6VTmKFXxJzbaP/view?usp=sharing below are instructions copied from our github repo for your convenience.

Requirements
------------
- Python 3.6+
- Standard library only (socket, sys, threading). No external packages per instructions except the cryptography (per the spec):

      pip install cryptography

- Everything else is standard library (base64, socket, sys, threading).

How to Run
----------
1. Start the server, passing it the TCP control port as the only argument:

       python server.py 8991

   The server creates its RSA 2048 keypair in memory and then listens:

       Starting server...
       Creating RSA keypair
       RSA keypair created
       Creating server socket
       Awaiting connections...

   Leave this terminal open.

2. In a separate terminal, start a client (no arguments). The client creates
   its own RSA keypair in memory on startup:

       python client.py

3. Connect to the server. The response carries the data port AND the
   server's public key, which the client stores for encrypting everything
   that follows:

       connect 127.0.0.1 8991
       200 status code received. Starting data connection on port <DATA PORT>

4. Log in. The login message (username + the client's public key) is
   encrypted with the server's public key before sending:

       login alice
       Received encrypted message
       200 status code received. Login successful

5. From this point on, every command is encrypted with the server's public
   key, and every response is encrypted with each client's own public key.
   Open more terminals and repeat steps 2-4 for more clients.

Client Commands
---------------
connect <ip> <port>            connect; receives data port + server public key
login <username>               register (sends your public key, encrypted)
who                            list all connected usernames
broadcast <message>            send an encrypted message to everyone
private <username> <message>   send an encrypted message to one user
quit                           disconnect and exit

How the Encryption Works
------------------------
- Both sides generate RSA 2048 keypairs in memory at startup.
- Keys are exchanged in the clear once: the server's public key rides in
  the connect response; the client's public key rides inside the (encrypted)
  login message.
- RSA-2048 with OAEP/SHA256 can only encrypt 190 bytes per block, so longer
  plaintexts (like login, which carries a PEM key) are split into 190-byte
  chunks and each chunk is encrypted separately.
- Ciphertext is binary, which would break the newline framing from the chat
  project - so each encrypted message is base64-encoded into a single line.
  One line on the wire = one encrypted message.
- Inside the encryption, messages use the exact same format as the chat
  project: status code, empty line, data section if required.

Notes
-----
- Start the server before connecting any client.
- Key generation takes a moment; wait for "Awaiting connections..." before
  connecting.
- Everything after connect is unreadable on the wire (see it in Wireshark:
  only the connect exchange is plaintext, the rest is base64 ciphertext).
- Keys live only in memory - restarting either side generates fresh keys.
- Stop the server with Ctrl+C when finished.