"""Static policy checks for MVI systemd pilot templates."""
from pathlib import Path


def validate(directory):
    directory=Path(directory)
    failures=[]
    for name in ('mvi-api.service','mvi-worker.service'):
        path=directory/name
        if not path.is_file():
            failures.append(name+': missing')
            continue
        data=path.read_text()
        for setting in ('User=mvi','Restart=always','NoNewPrivileges=true',
                        'ProtectSystem=strict','ProtectHome=true',
                        'ReadWritePaths=/var/lib/mvi','MemoryMax=2G',
                        'TasksMax=128','UMask=0077'):
            if setting not in data:failures.append(name+': missing '+setting)
    api=(directory/'mvi-api.service')
    if api.is_file():
        data=api.read_text()
        for setting in ('Environment=MVI_REQUIRE_AUTH=1',
                        'EnvironmentFile=/etc/mvi/api.env',
                        'ExecStart=/opt/ai-os/apps/mvi/.venv/bin/python'):
            if setting not in data:failures.append('mvi-api.service: missing '+setting)
    return failures

if __name__=='__main__':
    issues=validate(Path(__file__).parent)
    for issue in issues:print('FAIL:',issue)
    print('PASS: template policy' if not issues else 'FAIL: template policy')
    raise SystemExit(bool(issues))
