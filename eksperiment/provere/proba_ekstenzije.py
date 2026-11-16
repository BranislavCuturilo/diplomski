import glob, json, os, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
EXE = sorted(glob.glob(os.path.expanduser(r'~\.cursor\extensions\anthropic.claude-code-*-win32-x64\resources\native-binary\claude.exe')))[-1]
CLI = None
KOREN = r'C:\poredjenje-orkestrator'


def okruzenje(strana):
    e = {k: v for k, v in os.environ.items() if not k.upper().startswith(('CLAUDE', 'ANTHROPIC')) and k.upper() not in ('PWD', 'OLDPWD')}
    e.update(CLAUDE_CONFIG_DIR=os.path.join(KOREN, strana, 'config'), CLAUDE_CODE_AUTO_CONNECT_IDE='false',
             ENABLE_CLAUDEAI_MCP_SERVERS='false', DISABLE_AUTOUPDATER='1')
    return e


for strana in ('prazan', 'plugin'):
    cwd = os.path.join(KOREN, strana, 'projekat')
    print('===', strana)
    r = subprocess.run([EXE, 'auth', 'status', '--json'], cwd=cwd, env=okruzenje(strana), capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('auth', r.returncode, r.stdout.strip()[:220].replace('\n', ' '))
    r = subprocess.run([EXE, '-p', 'x', '--output-format', 'stream-json', '--verbose', '--no-session-persistence', '--model', 'haiku'],
                       cwd=cwd, env=okruzenje(strana), stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    for red in r.stdout.splitlines():
        try:
            z = json.loads(red)
        except ValueError:
            continue
        if z.get('subtype') == 'init':
            print('verzija', z.get('claude_code_version'), 'rezim', z.get('permissionMode'), 'cwd', z.get('cwd'))
            alati = set(z['tools'])
            print('alati', len(alati), 'delegiranje:', sorted(alati & {'Agent', 'Task', 'Skill', 'Workflow', 'SendMessage', 'ListAgents'}))
            print('skills', len(z.get('skills') or []), z.get('skills'))
            print('slash', len(z.get('slash_commands') or []))
            print('agents', z.get('agents'))
            print('plugins', [p.get('source') for p in z.get('plugins') or []], 'mcp', z.get('mcp_servers'))
        elif z.get('type') == 'result':
            print('result', str(z.get('result'))[:100], z.get('total_cost_usd'))
    if r.returncode and not r.stdout:
        print('stderr', r.stderr[-300:])
