CNT4713 - Project 2 - File Transfer Project
----------------------------------

Group Members
-------------
Jason Balladares - 5760817

Mahadi Rahman - 6406575

Phoenix Depaz - 6234251

Notes
-------------
here is where we have the source code hosted w/more instructions: https://github.com/jsonballadares/CNT4713/tree/main/Project%202
per the instructions on cavnas we will submit only the client.py server.py and readme.txt
and provide the url to our demo video here w/wireshark commentary: <TODO: add url here> below are instructions copied from our github repo for your convenience.

Requirements
------------
- Python 3.6+
- Standard library only (socket, sys, threading). No external packages per instructions
 
How to Run
----------
1. Start the server, passing it the TCP control port as the only argument:

       python server.py 8991

   The server prints:

       Starting server...
       Creating server socket
       Awaiting connections...

   On the first run it creates a folder named "server_files" next to
   server.py. This is the shared directory where uploaded files are stored
   and where list/retr/dele operate. Leave this terminal open.

2. In a separate terminal, start the client (no arguments):

       python client.py

   The client prints "Starting client..." and waits for commands.

3. Connect to the server using its IP address and the control port from
   step 1. On the same machine, use 127.0.0.1:

       connect 127.0.0.1 8991

   The server replies with a data port and the client connects to it:

       200 status code received. Starting data connection on port <DATA PORT>

4. Log in with a username:

       login alice

5. Run any of the file commands (see below). For stor, the file you want
   to upload must exist in the directory where you started the client.
   For retr, the downloaded file is saved into that same directory.

Client Commands
---------------
connect <ip> <port>   connect to the server (do this first)
login <username>      register a username with the server
list                  list the files currently on the server
stor <filename>       upload a local file to the server
retr <filename>       download a file from the server
dele <filename>       delete a file on the server
quit                  disconnect and exit

Notes
-----
- Start the server before connecting any client.
- The port on the connect command must match the port the server was
  started with.
- stor reads the file from the directory where the client was started;
  retr writes the downloaded file into that same directory.
- All uploaded files are stored in one shared "server_files" directory on
  the server, so files stored by one user can be listed and retrieved by
  another.
- stor fails (500) if the named local file does not exist; retr and dele
  fail (500) if the named file does not exist on the server.
- To run across machines, replace 127.0.0.1 with the server machine's IP
  and ensure the control port is reachable through any firewall.
- Stop the server with Ctrl+C when finished.