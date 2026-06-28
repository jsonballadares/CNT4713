#!/bin/bash
# validator.sh - quick correctness check, no extra tools needed.
# runs the file-transfer scenario (connect, login, list, stor, retr, dele)
# by piping commands into the client, then prints both outputs so they can be
# compared against the templates in the pdf. also verifies the files actually
# moved (upload landed on the server, download is byte-identical).
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

# fresh state each run
rm -rf server_files demo_run
mkdir -p server_files demo_run

# myfile.txt = the file the client will upload (lives next to the client)
echo "this is myfile.txt, uploaded by the validator" > demo_run/myfile.txt
# test.txt = a file pre-seeded on the server to download then delete
echo "this is test.txt, pre-seeded on the server" > server_files/test.txt
# keep a copy of what the download SHOULD produce, to verify integrity
cp server_files/test.txt demo_run/expected_test.txt

$PY server.py $PORT > server_out.txt 2>&1 &
SERVER_PID=$!
sleep 0.5

# the client runs from demo_run/ so uploaded/downloaded files stay contained
cd demo_run
( echo "connect 127.0.0.1 $PORT"; sleep 0.5
  echo "login alice";            sleep 0.5
  echo "list";                   sleep 0.5
  echo "stor myfile.txt";        sleep 1
  echo "list";                   sleep 0.5
  echo "retr test.txt";          sleep 1
  echo "dele test.txt";          sleep 0.5
  echo "list";                   sleep 0.5
  echo "quit";                   sleep 0.5
) | $PY ../client.py > ../client_out.txt 2>&1
cd ..

sleep 0.5
kill $SERVER_PID 2>/dev/null

echo "================= SERVER ================="
cat server_out.txt
echo
echo "================= CLIENT ================="
cat client_out.txt
echo
echo "============== FILE CHECKS ==============="
if [ -f server_files/myfile.txt ]; then
    echo "PASS: stor - myfile.txt landed in server_files/"
else
    echo "FAIL: stor - myfile.txt not found on server"
fi
if [ -f demo_run/test.txt ] && cmp -s demo_run/test.txt demo_run/expected_test.txt; then
    echo "PASS: retr - downloaded test.txt is byte-identical"
else
    echo "FAIL: retr - download missing or differs"
fi
if [ ! -f server_files/test.txt ]; then
    echo "PASS: dele - test.txt removed from server"
else
    echo "FAIL: dele - test.txt still on server"
fi