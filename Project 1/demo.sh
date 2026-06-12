#!/bin/bash
# demo.sh - runs the pdf scenario in three visible tmux panes:
#   left pane    = server
#   top right    = bob   (the receiving client)
#   bottom right = alice (the sending client)
#
# usage:
#   ./demo.sh           run with default pacing (3s between commands)
#   DELAY=6 ./demo.sh   slower pacing, e.g. while narrating a recording
#
# requires tmux (macOS: brew install tmux). run from the folder that
# contains server.py and client.py. detach/quit the session with: Ctrl+b d

SESSION=chatdemo
PORT=8991
DELAY=${DELAY:-3}
PY=${PY:-python3}

# start fresh
tmux kill-session -t $SESSION 2>/dev/null

# 1 window, 3 panes: 0 = left (server), 1 = top right (bob), 2 = bottom right (alice)
tmux new-session  -d -s $SESSION
tmux split-window -h -t $SESSION:0
tmux split-window -v -t $SESSION:0.1
tmux select-pane  -t $SESSION:0.0 -T "SERVER"
tmux select-pane  -t $SESSION:0.1 -T "BOB (receiver)"
tmux select-pane  -t $SESSION:0.2 -T "ALICE (sender)"
tmux set -t $SESSION pane-border-status top

# the scripted scenario runs in the background while we watch the session live
(
  sleep 1
  tmux send-keys -t $SESSION:0.0 "$PY server.py $PORT" C-m
  sleep 2

  # bob: connect and log in first (he is the receiver in the pdf scenario)
  tmux send-keys -t $SESSION:0.1 "$PY client.py" C-m
  sleep 1
  tmux send-keys -t $SESSION:0.1 "connect 127.0.0.1 $PORT" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.1 "login bob" C-m
  sleep $DELAY

  # alice: connect, log in, and run every command from the pdf
  tmux send-keys -t $SESSION:0.2 "$PY client.py" C-m
  sleep 1
  tmux send-keys -t $SESSION:0.2 "connect 127.0.0.1 $PORT" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.2 "login alice" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.2 "who" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.2 "broadcast Hello all!" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.2 "private bob Lets talk" C-m
  sleep $DELAY
  tmux send-keys -t $SESSION:0.2 "quit" C-m
  sleep $DELAY

  # bob quits last
  tmux send-keys -t $SESSION:0.1 "quit" C-m
) &

# attach so the whole scenario plays out on screen (this is what you record)
tmux attach -t $SESSION