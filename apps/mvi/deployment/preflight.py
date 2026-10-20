"""Non-destructive preflight for MVI private single-host Linux deployment."""
import argparse
import os
import shutil
import sys
from pathlib import Path


def check(root,require_auth=True):
    problems=[]
    root=Path(root)
    if not root.exists() or not root.is_dir():
        problems.append('MVI data directory missing')
    elif not os.access(root,os.W_OK):
        problems.append('MVI data directory not writable')
    for program in ('ffmpeg','ffprobe'):
        if shutil.which(program) is None:
            problems.append(program+' unavailable')
    if require_auth and not os.environ.get('MVI_API_TOKEN'):
        problems.append('MVI_API_TOKEN missing')
    if os.environ.get('MVI_DURABLE_QUEUE')!='1':
        problems.append('MVI_DURABLE_QUEUE must equal 1')
    return problems


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default=os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))
    parser.add_argument('--local-only',action='store_true')
    args=parser.parse_args()
    problems=check(args.root,require_auth=not args.local_only)
    for problem in problems:print('FAIL:',problem)
    if problems:return 1
    print('PASS: static MVI private-host preflight; runtime and security verification still required')
    return 0

if __name__=='__main__':sys.exit(main())
