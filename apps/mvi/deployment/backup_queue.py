"""Consistent offline-copy backup of the live MVI SQLite queue.

Use SQLite's backup API, never copy the WAL database file while in use.
"""
import argparse
from contextlib import closing
import os
import sqlite3
import tempfile
from pathlib import Path


def backup(source, destination):
    source=Path(source)
    destination=Path(destination)
    if not source.is_file():
        raise FileNotFoundError('Queue database does not exist')
    if source.resolve()==destination.resolve():
        raise ValueError('Source and destination must differ')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if destination.exists():
        raise FileExistsError('Refusing to overwrite existing backup')
    fd,temporary=tempfile.mkstemp(prefix='.mvi-backup-',suffix='.db',dir=destination.parent)
    os.fchmod(fd,0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(f'file:{source}?mode=ro',uri=True,timeout=15)) as original:
            with closing(sqlite3.connect(temporary,timeout=15)) as copy:
                original.backup(copy)
                result=copy.execute('PRAGMA integrity_check').fetchone()[0]
                if result!='ok':raise RuntimeError('Backup integrity check failed: '+result)
        os.link(temporary,destination)  # Never overwrite an existing backup.
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    path=backup(Path(args.root)/'private'/'queue.db',args.output)
    print('Queue snapshot created:',path)

if __name__=='__main__':main()
