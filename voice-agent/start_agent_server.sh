#!/bin/bash
# Start the AudioSocket agent server inside the freepbx container.
LOG=/var/log/asterisk/ai_agent.log
pkill -f "python3 -m agent[.]server" 2>/dev/null
pkill -f "agent_server[.]py" 2>/dev/null
sleep 1
cd /opt/voice-agent || exit 1
LD_LIBRARY_PATH=/opt/voice-agent/piper/numpy.libs setsid nohup python3 -m agent.server >>"$LOG" 2>&1 < /dev/null &
sleep 2
if pgrep -f "python3 -m agent[.]server" >/dev/null; then
    echo "agent_server started at $(date)" >>"$LOG"
else
    echo "agent_server FAILED to start at $(date)" >>"$LOG"
fi
