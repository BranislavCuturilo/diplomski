import sys,json
for r in sys.stdin:
    try: z=json.loads(r)
    except ValueError: continue
    if z.get('subtype')=='init':
        print('verzija',z.get('claude_code_version'),'rezim',z.get('permissionMode'),'model',z.get('model'),'cwd',z.get('cwd'))
        print('alati',len(z['tools']),sorted(z['tools']))
        print('skills',len(z.get('skills') or []),z.get('skills'))
        print('slash',len(z.get('slash_commands') or []),(z.get('slash_commands') or [])[:40])
        print('agents',z.get('agents'))
        print('plugins',[p.get('source') for p in z.get('plugins') or []],'mcp',z.get('mcp_servers'))
    elif z.get('type')=='result': print('result',str(z.get('result'))[:100],z.get('total_cost_usd'))
