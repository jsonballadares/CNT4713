#!/bin/bash
# demo.sh - runs the file-transfer scenario in two visible tmux panes:
#   left pane  = server
#   right pane = alice (runs every FTP command from the pdf)
#
# usage (from anywhere):
#   ./demo.sh           run with default pacing (3s between commands)
#   DELAY=6 ./demo.sh   slower pacing, e.g. while narrating a recording
#   KEEP=1 ./demo.sh    keep the demo files afterward (skip cleanup)
#
# requires tmux (macOS: brew install tmux).
# expects server.py / client.py either next to this script or in ./src.
# detach/quit the session with: Ctrl+b d
#
# everything this script creates (myfile.txt, server_files/, the demo
# download) is removed on exit so each run starts from a clean slate.

SESSION=ftdemo
PORT=8991
DELAY=${DELAY:-3}
PY=${PY:-python3}

# find the folder with the code, relative to where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/server.py" ]; then
    SRC="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/src/server.py" ]; then
    SRC="$SCRIPT_DIR/src"
else
    echo "error: cannot find server.py (looked in '$SCRIPT_DIR' and '$SCRIPT_DIR/src')"
    exit 1
fi
echo "using code in: $SRC"

# cleanup() removes everything the demo created and kills the tmux session.
# it runs on ANY exit (normal, Ctrl+C, or error) via the trap below, so the
# demo leaves no files behind. set KEEP=1 to skip it.
cleanup() {
    tmux kill-session -t $SESSION 2>/dev/null
    if [ -z "$KEEP" ]; then
        rm -f "$SRC/myfile.txt"      # the file the client uploaded
        rm -f "$SRC/test.txt"        # the file the client downloaded via retr
        rm -rf "$SRC/server_files"   # the server's shared storage dir
        echo "cleaned up demo files."
    fi
}
trap cleanup EXIT INT TERM

# the client uploads myfile.txt and downloads test.txt, so make sure both
# exist: myfile.txt next to the client (to upload), test.txt pre-seeded in
# the server's shared directory (to download and then delete)
rm -rf "$SRC/server_files"
echo "this is myfile.txt, uploaded by the demo client" > "$SRC/myfile.txt"
mkdir -p "$SRC/server_files"
echo "this is test.txt, pre-seeded on the server" > "$SRC/server_files/test.txt"

# start fresh; both panes start inside $SRC (-c sets the start directory)
tmux kill-session -t $SESSION 2>/dev/null
tmux new-session  -d -s $SESSION -c "$SRC"
tmux split-window -h -t $SESSION:0 -c "$SRC"
tmux select-pane  -t $SESSION:0.0 -T "SERVER"
tmux select-pane  -t $SESSION:0.1 -T "ALICE (client)"
tmux set -t $SESSION pane-border-status top

# the scripted scenario runs in the background while we watch the session live
(
  sleep 1
  tmux send-keys -t $SESSION:0.0 "$PY server.py $PORT" C-m
  sleep 2

  # alice: connect, log in, and run every file command from the pdf
  tmux send-keys -t $SESSION:0.1 "$PY client.py" C-m
  sleep 1
  tmux send-keys -t $SESSION:0.1 "connect 127.0.0.1 $PORT" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "login alice" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "list" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "stor myfile.txt" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "list" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "retr test.txt" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "dele test.txt" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "list" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "quit" C-m
) &

# attach so the whole scenario plays out on screen (this is what you record).
# when you detach or the session ends, the trap above cleans everything up.
tmux attach -t $SESSION