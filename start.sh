#!/bin/bash
# 666 是特权端口，需要 sudo；也可 ./start.sh 127.0.0.1 8666 用普通端口
cd "$(dirname "$0")"
PORT=${2:-666}
if [ "$PORT" -lt 1024 ]; then exec sudo python3 server.py "${1:-127.0.0.1}" "$PORT"; else exec python3 server.py "${1:-127.0.0.1}" "$PORT"; fi
