"""Run the authenticated API and durable worker as supervised processes on Render."""
import os
import signal
import subprocess
import sys
import time

children = []
stopping = False

def stop(*_):
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.terminate()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

env = os.environ.copy()
env.setdefault("MVI_BIND_HOST", "0.0.0.0")
env.setdefault("MVI_DATA_DIR", "/var/lib/mvi")
env.setdefault("MVI_DURABLE_QUEUE", "1")
api = subprocess.Popen([sys.executable, "server.py"], env=env)
worker = subprocess.Popen([sys.executable, "durable_runtime.py"], env=env)
children[:] = [api, worker]

while not stopping:
    exited = next((child for child in children if child.poll() is not None), None)
    if exited is not None:
        code = exited.returncode or 1
        for child in children:
            if child is not exited and child.poll() is None:
                child.terminate()
        raise SystemExit(code)
    time.sleep(1)

for child in children:
    child.wait()
