CNT4713 - Project 1 - Chat Project
====================

Group Members
-------------
Jason Balladares - 5760817

Mahadi Rahman - <Panther-ID>

Phoenix Depaz - <Panther-ID>

Demo
----
https://github.com/user-attachments/assets/a455892b-e7fc-45d2-a7b2-8d6d4874e1ba



Files
-----
server.py  -  the chat server
client.py  -  the chat client
 
Requirements
------------
- Python 3.6+
- Standard library only (socket, sys, threading). No external packages per instructions
 
How to Run
----------
1. Start the server first. Pass it the TCP control port as the only
   command line argument:
 
       python server.py 8991
 
   The server prints:
 
       Starting server...
       Creating server socket
       Awaiting connections...
 
   and then waits. Leave this terminal open.
 
2. In a separate terminal, start a client (no arguments):
 
       python client.py
 
   The client prints "Starting client..." and waits for commands.
 
3. In the client, connect to the server using the server's IP address
   and the control port from step 1. If everything is running on the
   same machine, use 127.0.0.1:
 
       connect 127.0.0.1 8991
 
   The server responds with the data port and the client connects to it
   automatically:
 
       200 status code received. Starting data connection on port <DATA PORT>
 
4. Log in with a username (must be unique among connected users):
 
       login alice
 
5. You can open more terminals and repeat steps 2-4 to connect more
   clients (e.g. login bob in a second client).
 
Client Commands
---------------
connect <ip> <control_port>       connect to the server (do this first)
login <username>               register a username with the server
who                            list all connected usernames
broadcast <message>            send a message to everyone
private <username> <message>   send a message to one user
quit                           disconnect and exit
 
Notes
-----
- The server must be started before any client tries to connect.
- The port number on the connect command must match the control port 
  the server was started with.
- To run the server and clients on different machines, replace
  127.0.0.1 with the server machine's IP address and make sure the
  control port is reachable via network as firewall may block.
- Usernames must be unique; logging in with a name that is taken
  returns a 500 and you can try a different name.
- demo.sh will be used to showcase the project running and the validator
  serves as a regression for extending the code with confidence.
  use chmod +x validator.sh or chmod +x demo.sh then ./demo.sh or ./validator.sh
- Stop the server with Ctrl+C when finished.
