#!/bin/bash
# validator.sh - quick correctness check, no extra tools needed.
# runs the pdf scenario (bob receiving, alice sending) by piping commands
# into the client processes with delays, then prints all three outputs so
# they can be compared against the templates in the pdf.
#
# usage (from anywhere): ./validator.sh
# expects server.py / client.py either next to this script or in ./src.

PORT=8991
PY=${PY:-python3}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/server.py" ]; then
    SRC="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/src/server.py" ]; then
    SRC="$SCRIPT_DIR/src"
else
    echo "error: cannot find server.py (looked in '$SCRIPT_DIR' and '$SCRIPT_DIR/src')"
    exit 1
fi
cd "$SRC" || exit 1
echo "using code in: $SRC"

$PY server.py $PORT > server_out.txt 2>&1 &
SERVER_PID=$!
sleep 0.5

# bob: connects, logs in, sits long enough to receive alice's messages, quits
( echo "connect 127.0.0.1 $PORT"; sleep 0.5
  echo "login bob";               sleep 4
  echo "quit" ) | $PY client.py > bob_out.txt 2>&1 &
BOB_PID=$!
sleep 1

# alice: runs every command from the pdf
( echo "connect 127.0.0.1 $PORT";   sleep 0.5
  echo "login alice";               sleep 0.5
  echo "who";                       sleep 0.5
  echo "broadcast Hello all!";      sleep 0.5
  echo "private bob Lets talk";     sleep 0.5
  echo "quit" ) | $PY client.py > alice_out.txt 2>&1

wait $BOB_PID
sleep 0.5
kill $SERVER_PID 2>/dev/null

echo "================= SERVER ================="
cat server_out.txt
echo
echo "============ ALICE (sender) =============="
cat alice_out.txt
echo
echo "============= BOB (receiver) ============="
cat bob_out.txt