"""Atomic local job-state persistence for the MVI prototype."""
import json
import os
import tempfile
from pathlib import Path


def save(directory, state):
 directory=Path(directory)
 fd, temporary=tempfile.mkstemp(prefix='.job-',suffix='.tmp',dir=directory)
 try:
  with os.fdopen(fd,'w') as output:
   json.dump(state,output,indent=2)
   output.flush()
   os.fsync(output.fileno())
  os.replace(temporary,directory/'job.json')
 finally:
  if os.path.exists(temporary):
   os.unlink(temporary)


def load(path):
 """A stopped local worker must not masquerade as still running."""
 state=json.loads(Path(path).read_text())
 if state.get('status') in {'queued','retrieving','running','compiling_timeline','reviewing_frames'}:
  state=dict(state,status='interrupted',recovery='Worker stopped. Manual resubmission required; automatic retries not implemented.')
 return state
