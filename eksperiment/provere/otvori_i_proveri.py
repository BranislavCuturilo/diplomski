"""Otvara obe strane kroz otvori.cmd i cita okruzenje stvarnih procesa ekstenzije. Ne poziva model."""
import os, subprocess, sys, time

sys.stdout.reconfigure(encoding='utf-8')
try:
    import psutil
except ImportError:
    print('NEMA_PSUTIL')
    sys.exit(3)

KOREN = r'C:\poredjenje-orkestrator'
env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('CLAUDE', 'ANTHROPIC')) and k.upper() not in ('PWD', 'OLDPWD')}
for strana in ('prazan', 'plugin'):
    subprocess.run(['cmd', '/c', os.path.join(KOREN, strana, 'otvori.cmd')], env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    time.sleep(12)
time.sleep(15)

nasao = 0
for p in psutil.process_iter(['name', 'cmdline']):
    if (p.info['name'] or '').lower() != 'cursor.exe':
        continue
    cmd = ' '.join(p.info['cmdline'] or [])
    if 'utility-sub-type=node.mojom.NodeService' not in cmd:
        continue
    try:
        e = p.environ()
    except psutil.Error as g:
        print('pid', p.pid, 'nije citljivo', g)
        continue
    if e.get('VSCODE_ESM_ENTRYPOINT', e.get('VSCODE_AMD_ENTRYPOINT', '')).find('extensionHost') < 0 and 'extensionHost' not in cmd and e.get('VSCODE_CRASH_REPORTER_PROCESS_TYPE') != 'extensionHost':
        continue
    nasao += 1
    print('ext host pid', p.pid, '| CLAUDE_CONFIG_DIR =', e.get('CLAUDE_CONFIG_DIR'), '| VIRTUAL_ENV =', e.get('VIRTUAL_ENV'), '| PWD =', e.get('PWD'), '| AUTO_IDE =', e.get('CLAUDE_CODE_AUTO_CONNECT_IDE'), '| CLAUDECODE =', e.get('CLAUDECODE'))
print('procesa ekstenzije:', nasao)
