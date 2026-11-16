# -*- coding: utf-8 -*-
"""Testovi hookova, faza i izvestaja. Bez modela i bez mreze, samo privremeni folderi.

    python -m unittest discover -s tests

JSON ulazi imaju oblik snimljen iz stvarne sesije Claude Code 2.1.296.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, unittest

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POKRENI = os.path.join(KOREN, 'hooks', 'pokreni.py')
SVI = ['pull', 'ruter', 'upit', 'skill', 'git', 'upotreba', 'stop', 'sync']
UPIT = 'Dodaj model grupe, Čačak šuma ћирилица'


def citaj(put):
    with open(put, encoding='utf-8') as f:
        return [json.loads(r) for r in f if r.strip()]


class Osnova(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='diplomski-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.projekat = os.path.join(self.tmp, 'projekat')
        os.makedirs(os.path.join(self.projekat, '.claude'))
        with open(os.path.join(self.projekat, '.claude', 'diplomski-projekat'), 'w') as f:
            f.write('x')
        self.bez = os.path.join(self.tmp, 'bez')
        os.makedirs(self.bez)
        self.usage = os.path.join(self.projekat, '.claude', 'usage')

    def hook(self, ime, ulaz, projekat=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=projekat or self.projekat, CLAUDE_PLUGIN_ROOT=KOREN)
        env.pop('PYTHONUTF8', None)
        env.pop('PYTHONIOENCODING', None)
        return subprocess.run([sys.executable, POKRENI, ime], input=json.dumps(ulaz, ensure_ascii=False).encode('utf-8'),
                              capture_output=True, env=env)

    def transkript(self, sesija, redovi, podagent=None):
        if podagent:
            folder = os.path.join(self.tmp, 't', sesija, 'subagents')
            ime = 'agent-%s.jsonl' % podagent
        else:
            folder = os.path.join(self.tmp, 't')
            ime = sesija + '.jsonl'
        os.makedirs(folder, exist_ok=True)
        put = os.path.join(folder, ime)
        with open(put, 'w', encoding='utf-8') as f:
            for r in redovi:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        return put

    def edit(self, fajl, transcript_path, **dodatno):
        return dict({'session_id': 's1', 'transcript_path': transcript_path, 'cwd': self.projekat, 'hook_event_name': 'PreToolUse',
                     'tool_name': 'Edit', 'tool_input': {'file_path': fajl, 'old_string': 'a', 'new_string': 'b'}}, **dodatno)


class BezMarkera(Osnova):
    def test_svaki_hook_je_tih_i_nista_ne_pise(self):
        # svaki ulaz koji bi sa markerom izazvao odbijanje ili upis
        ulaz = {'session_id': 's', 'cwd': self.bez, 'prompt': 'model grupe', 'tool_name': 'Bash',
                'tool_input': {'command': 'git add -A', 'file_path': 'a/models.py'}, 'transcript_path': 'nema'}
        for ime in SVI:
            r = self.hook(ime, ulaz, projekat=self.bez)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b'', b''), ime)
        self.assertEqual(os.listdir(self.bez), [])

    def test_kontrola_isti_ulaz_sa_markerom_odbija(self):
        r = self.hook('git', {'cwd': self.projekat, 'tool_input': {'command': 'git add -A'}})
        self.assertIn(b'"deny"', r.stdout)


class Upit(Osnova):
    def test_upis_jednog_reda_sa_celim_tekstom(self):
        r = self.hook('upit', {'session_id': 's1', 'cwd': self.projekat, 'hook_event_name': 'UserPromptSubmit', 'prompt': UPIT})
        self.assertEqual((r.returncode, r.stdout), (0, b''))
        redovi = citaj(os.path.join(self.usage, 'prompts.jsonl'))
        self.assertEqual(len(redovi), 1)
        self.assertEqual(redovi[0]['tekst'], UPIT)
        self.assertEqual(redovi[0]['duzina'], len(UPIT))
        self.assertEqual(redovi[0]['sesija'], 's1')
        self.assertIsNone(redovi[0]['faza'])

    def test_obavestenje_o_zadatku_nije_upit(self):
        r = self.hook('upit', {'session_id': 's1', 'cwd': self.projekat, 'prompt': '<task-notification>\n<task-id>a1</task-id>'})
        self.assertEqual((r.returncode, r.stdout), (0, b''))
        self.assertFalse(os.path.exists(os.path.join(self.usage, 'prompts.jsonl')))

    def test_nikad_ne_blokira_ni_kad_upis_ne_moze(self):
        # folder usage zamenjen fajlom: makedirs i open moraju da padnu
        with open(self.usage, 'w') as f:
            f.write('x')
        r = self.hook('upit', {'session_id': 's1', 'cwd': self.projekat, 'prompt': UPIT})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b'', b''))

    def test_nikad_ne_blokira_na_neispravnom_ulazu(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.projekat)
        r = subprocess.run([sys.executable, POKRENI, 'upit'], input=b'\xff\xfe nije json', capture_output=True, env=env)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b'', b''))


class Faza(Osnova):
    def faza(self, *a, cwd=None):
        return subprocess.run([sys.executable, os.path.join(KOREN, 'scripts', 'faza.py'), *a], capture_output=True,
                              cwd=cwd or self.projekat, env={k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'})

    def test_upis_i_faza_u_upitu(self):
        self.assertEqual(self.faza('kontrolni', 'skup').returncode, 0)
        self.assertEqual(citaj(os.path.join(self.usage, 'faze.jsonl'))[0]['faza'], 'kontrolni skup')
        self.hook('upit', {'session_id': 's', 'cwd': self.projekat, 'prompt': 'x'})
        self.assertEqual(citaj(os.path.join(self.usage, 'prompts.jsonl'))[0]['faza'], 'kontrolni skup')

    def test_nepoznata_faza_i_bez_markera_odbijaju(self):
        self.assertEqual(self.faza('rucak').returncode, 2)
        self.assertFalse(os.path.exists(self.usage))
        self.assertEqual(self.faza('planiranje', cwd=self.bez).returncode, 2)
        self.assertEqual(os.listdir(self.bez), [])


class RequireSkill(Osnova):
    PRELOAD = {'type': 'user', 'isSidechain': True, 'message': {'role': 'user', 'content': [
        {'type': 'text', 'text': '<command-message>ui-bootstrap</command-message>\n<command-name>ui-bootstrap</command-name>\n<skill-format>true</skill-format>'},
        {'type': 'text', 'text': 'Base directory for this skill: ...'}]}}

    def podagent(self, fajl, redovi):
        roditelj = self.transkript('s1', [{'type': 'user', 'message': {'role': 'user', 'content': 'x'}}])
        self.transkript('s1', redovi, podagent='a1')
        return self.hook('skill', self.edit(fajl, roditelj, agent_id='a1', agent_type='diplomski:frontend-junior'))

    def test_skill_iz_zaglavlja_agenta_prolazi(self):
        r = self.podagent('C:\\p\\static\\site.css', [self.PRELOAD])
        self.assertEqual((r.returncode, r.stdout), (0, b''))

    def test_podagent_bez_skilla_odbijen_sa_putanjom_za_read(self):
        r = self.podagent('C:\\p\\app.py', [self.PRELOAD])
        izlaz = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual(izlaz['permissionDecision'], 'deny')
        self.assertIn('craft-code/SKILL.md', izlaz['permissionDecisionReason'])

    def test_podagent_koji_procita_skill_prolazi(self):
        read = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'C:\\p\\skills\\opsti-sloj\\craft-code\\SKILL.md'}}]}}
        r = self.podagent('C:\\p\\app.py', [read])
        self.assertEqual(r.stdout, b'')

    def test_glavni_tok_read_ne_vazi_skill_alat_vazi(self):
        read = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'C:/x/craft-code/SKILL.md'}}]}}
        t = self.transkript('g', [read])
        self.assertIn(b'"deny"', self.hook('skill', self.edit('a/app.py', t)).stdout)
        skill = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'diplomski:craft-code'}}]}}
        t = self.transkript('g', [skill])
        self.assertEqual(self.hook('skill', self.edit('a/app.py', t)).stdout, b'')

    def test_tekst_skills_u_upitu_nije_ucitan_skill(self):
        red = {'type': 'user', 'message': {'role': 'user', 'content': 'pise skills: craft-code u zaglavlju'}}
        t = self.transkript('g', [red])
        self.assertIn(b'"deny"', self.hook('skill', self.edit('a/app.py', t)).stdout)

    def test_motor_trazi_domen_a_test_motora_craft_testing(self):
        t = self.transkript('g', [])
        self.assertIn('projekat-domen', json.loads(self.hook('skill', self.edit('a/igra/motor.py', t)).stdout)['hookSpecificOutput']['permissionDecisionReason'])
        self.assertIn('craft-testing', json.loads(self.hook('skill', self.edit('a/igra/tests/test_motor.py', t)).stdout)['hookSpecificOutput']['permissionDecisionReason'])

    def test_skripta_igre_trazi_spoj_sa_bootstrapom(self):
        t = self.transkript('g', [])
        self.assertIn('django-ssr-bootstrap', json.loads(self.hook('skill', self.edit('a/static/igra/igra.js', t)).stdout)['hookSpecificOutput']['permissionDecisionReason'])

    def test_podagent_dobija_putanju_projektnog_skilla(self):
        put = os.path.join(self.projekat, '.claude', 'skills', 'projekat-domen')
        os.makedirs(put)
        open(os.path.join(put, 'SKILL.md'), 'w').close()
        r = self.podagent('C:\\p\\igra\\motor.py', [self.PRELOAD])
        self.assertIn(self.projekat.replace('\\', '/') + '/.claude/skills/projekat-domen/SKILL.md', r.stdout.decode('utf-8'))

    def test_necitljiv_transkript_ne_blokira(self):
        self.assertEqual(self.hook('skill', self.edit('a/app.py', os.path.join(self.tmp, 'nema.jsonl'))).stdout, b'')

    def test_slovo_c_sa_kvacicom_u_putanji(self):
        t = self.transkript('g', [])
        self.assertIn(b'"deny"', self.hook('skill', self.edit('a/Čačak/app.py', t)).stdout)


class OstaliHookovi(Osnova):
    def test_git_guard(self):
        for kom in ('git add -A', 'git push --force origin x', 'git reset --hard HEAD~1'):
            self.assertIn(b'"deny"', self.hook('git', {'cwd': self.projekat, 'tool_name': 'PowerShell', 'tool_input': {'command': kom}}).stdout, kom)
        self.assertEqual(self.hook('git', {'cwd': self.projekat, 'tool_input': {'command': 'git add a.py'}}).stdout, b'')

    def test_ruter_predlaze_na_cirilici_i_latinici(self):
        izlaz = json.loads(self.hook('ruter', {'cwd': self.projekat, 'prompt': UPIT}).stdout)
        self.assertIn('stack-django', izlaz['hookSpecificOutput']['additionalContext'])

    def test_log_usage_cita_total_tokens(self):
        self.hook('upotreba', {'session_id': 's', 'cwd': self.projekat, 'tool_name': 'Agent', 'tool_input': {'subagent_type': 'diplomski:qa'},
                               'tool_response': {'status': 'completed', 'totalTokens': 12390, 'usage': {'output_tokens': 5}}})
        red = citaj(os.path.join(self.usage, 'usage.jsonl'))[0]
        self.assertEqual((red['ime'], red['tokeni']), ('diplomski:qa', 12390))

    def test_stop_odbija_jednom(self):
        red = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'a.py'}}]}}
        t = self.transkript('g', [red])
        self.assertIn(b'"block"', self.hook('stop', {'cwd': self.projekat, 'transcript_path': t, 'stop_hook_active': False}).stdout)
        self.assertEqual(self.hook('stop', {'cwd': self.projekat, 'transcript_path': t, 'stop_hook_active': True}).stdout, b'')

    IZMENA = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'igra/motor.py'}}]}}

    def shell(self, alat, komanda='python manage.py test'):
        return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': alat, 'input': {'command': komanda}}]}}

    def stop(self, t):
        return self.hook('stop', {'cwd': self.projekat, 'transcript_path': t, 'stop_hook_active': False}).stdout

    def test_stop_testovi_kroz_powershell_vaze(self):
        self.assertEqual(self.stop(self.transkript('g', [self.IZMENA, self.shell('PowerShell')])), b'')

    def test_stop_druga_komanda_nije_test(self):
        self.assertIn(b'"block"', self.stop(self.transkript('g', [self.IZMENA, self.shell('PowerShell', 'dir')])))

    def test_stop_kod_u_podagentu_bez_testova_odbija(self):
        t = self.transkript('g', [])
        self.transkript('g', [self.IZMENA], podagent='a1')
        self.assertIn(b'"block"', self.stop(t))

    def test_stop_kod_i_testovi_u_razlicitim_podagentima_prolazi(self):
        t = self.transkript('g', [])
        self.transkript('g', [self.IZMENA], podagent='a1')
        self.transkript('g', [self.shell('Bash', 'python "x/tools/test_summary.py"')], podagent='a2')
        self.assertEqual(self.stop(t), b'')

    def test_stop_izmena_plana_koji_pominje_py_nije_kod(self):
        plan = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit',
                'input': {'file_path': 'plan.md', 'new_string': 'backend pise igra/motor.py i views.py'}}]}}
        self.assertEqual(self.stop(self.transkript('g', [plan])), b'')

    def agent_u_pozadini(self, id_='t1'):
        return [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': id_, 'name': 'Agent',
                 'input': {'description': 'devops ispravke', 'subagent_type': 'diplomski:devops'}}]}},
                {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': id_,
                 'content': [{'type': 'text', 'text': 'Async agent launched successfully.\nagentId: a%s (internal ID)' % id_}]}]}}]

    def test_stop_ne_trazi_testove_dok_agenti_rade(self):
        izlaz = json.loads(self.stop(self.transkript('g', [self.IZMENA] + self.agent_u_pozadini())))
        self.assertNotIn('decision', izlaz)
        self.assertIn('RADI JOS', izlaz['systemMessage'])

    def test_stop_predat_izvestaj_je_kraj_agenta(self):
        predao = {'type': 'user', 'message': {'content': 'Another Claude session sent a message:\n<agent-message from="at1">\n'
                                                         '[Subagent hand-back] izvestaj'}}
        self.assertEqual(self.stop(self.transkript('g', self.agent_u_pozadini() + [predao])), b'')

    def test_stop_javlja_coveku_dok_agent_radi_i_ne_blokira(self):
        izlaz = json.loads(self.stop(self.transkript('g', self.agent_u_pozadini())))
        self.assertIn('RADI JOS: 1 podagent(a): devops ispravke', izlaz['systemMessage'])
        self.assertNotIn('decision', izlaz)

    def test_stop_ne_javlja_kada_je_agent_zavrsio(self):
        kraj = {'type': 'user', 'message': {'content': '<task-notification>\n<task-id>x</task-id>\n<tool-use-id>t1</tool-use-id>\n'
                                                       '<status>completed</status>\n</task-notification>'}}
        self.assertEqual(self.stop(self.transkript('g', self.agent_u_pozadini() + [kraj])), b'')

    def test_upit_ne_belezi_izvestaj_podagenta(self):
        for tekst in ('Another Claude session sent a message:\n<agent-message from="a1">', '<agent-message from="a1">x'):
            self.hook('upit', {'session_id': 's1', 'cwd': self.projekat, 'prompt': tekst})
        self.assertFalse(os.path.exists(os.path.join(self.usage, 'prompts.jsonl')))

    def test_ruter_prepoznaje_pocetni_upit(self):
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import priprema_poredjenja
        izlaz = json.loads(self.hook('ruter', {'cwd': self.projekat, 'prompt': priprema_poredjenja.UPIT}).stdout)['hookSpecificOutput']['additionalContext']
        for ime in ('projekat-domen', 'projekat-standardi', 'planer'):
            self.assertIn(ime, izlaz)


class Mapa(Osnova):
    DATOTEKE = {
        'MVP.md': '# MVP: igra\n\ntekst\n',
        'app/urls.py': "from django.urls import path\nurlpatterns = [path('stat/', views.stat, name='stat')]\n",
        'app/models.py': ('from django.db import models\nclass Partija(models.Model):\n    seme = models.CharField(max_length=9)\n'
                          '    vlasnik = models.ForeignKey("x", on_delete=models.CASCADE)\n'),
        'app/views.py': 'def stat(request):\n    return 1\n',
        'app/migrations/0001_initial.py': '', 'app/migrations/0002_dodatak.py': '',
        'app/tests/test_tok.py': 'import playwright\ndef test_a(): pass\ndef test_b(): pass\n',
        'app/templates/app/x.html': '{% extends "app/osnova.html" %}\n<p>x</p>\n',
        'app/locale/en/LC_MESSAGES/django.po': 'msgid ""\nmsgstr ""\nmsgid "a"\nmsgstr "b"\n',
        'venv/lib/skriveno.py': 'def ne_sme(): pass\n',
    }

    def test_mapa_nosi_sta_gde_stoji_bez_venv(self):
        for put, sadrzaj in self.DATOTEKE.items():
            os.makedirs(os.path.dirname(os.path.join(self.bez, put)) or self.bez, exist_ok=True)
            with open(os.path.join(self.bez, put), 'w', encoding='utf-8') as f:
                f.write(sadrzaj)
        r = subprocess.run([sys.executable, os.path.join(KOREN, 'tools', 'mapa.py'), self.bez], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        for ocekivano in ('`MVP.md` (2 redova): MVP: igra', '`/stat/` -> `views.stat` ime `stat`', '`Partija` (`app/models.py`): seme, vlasnik',
                          '`app/views.py` (2 redova): funkcije stat', '`app/tests/test_tok.py`: 2 testova [pregledac]',
                          '`app`: 2, poslednja `0002_dodatak`', 'nasledjuje `app/osnova.html`', 'django.po`: 1 poruka'):
            self.assertIn(ocekivano, r.stdout)
        self.assertNotIn('ne_sme', r.stdout)


class TestSummary(Osnova):
    MANAGE = 'import sys, unittest\nsys.exit(0 if unittest.main(module=None, argv=["x", "discover", "-p", "t_*.py"], exit=False).result.wasSuccessful() else 1)\n'
    TEST = 'import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, %d)\n'

    def pokreni(self, ocekivano):
        with open(os.path.join(self.bez, 'manage.py'), 'w') as f:
            f.write(self.MANAGE)
        with open(os.path.join(self.bez, 't_a.py'), 'w') as f:
            f.write(self.TEST % ocekivano)
        return subprocess.run([sys.executable, os.path.join(KOREN, 'tools', 'test_summary.py')], cwd=self.bez, capture_output=True, text=True, encoding='utf-8')

    def test_prolaz(self):
        r = self.pokreni(1)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('1 pokrenuto, 0 palo', r.stdout)

    # Laznjak manage.py: sa oznakama pokrece samo njih, bez oznaka sve iz paketa tests.
    MANAGE_OZNAKE = ('import sys, unittest\noznake = [a for a in sys.argv[2:] if not a.startswith("-")]\n'
                     'argv = ["x"] + oznake if oznake else ["x", "discover", "-s", "tests", "-t", "."]\n'
                     'sys.exit(0 if unittest.main(module=None, argv=argv, exit=False).result.wasSuccessful() else 1)\n')

    def brzo(self, *dodatno):
        os.makedirs(os.path.join(self.bez, 'tests'), exist_ok=True)
        for ime, sadrzaj in (('manage.py', self.MANAGE_OZNAKE), (os.path.join('tests', '__init__.py'), ''),
                             (os.path.join('tests', 'test_a.py'), self.TEST % 1),
                             (os.path.join('tests', 'test_b.py'), '# playwright\n' + self.TEST % 2)):
            with open(os.path.join(self.bez, ime), 'w') as f:
                f.write(sadrzaj)
        return subprocess.run([sys.executable, os.path.join(KOREN, 'tools', 'test_summary.py'), *dodatno], cwd=self.bez,
                              capture_output=True, text=True, encoding='utf-8')

    def test_brzo_preskace_modul_sa_pregledacem(self):
        r = self.brzo('--brzo')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('1 pokrenuto, 0 palo', r.stdout)
        self.assertIn(os.path.join('tests', 'test_b.py'), r.stdout)

    def test_bez_brzo_pokrece_i_pregledac(self):
        r = self.brzo()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('2 pokrenuto, 1 palo', r.stdout)

    def test_pad_nosi_izlazni_kod_i_ime_testa(self):
        r = self.pokreni(2)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('1 pokrenuto, 1 palo', r.stdout)
        self.assertIn('test_a', r.stdout)


def poruka(mid, t, model='claude-haiku-5-5', izlaz=10, sadrzaj=None, **u):
    return {'type': 'assistant', 'timestamp': t, 'message': {'id': mid, 'model': model, 'content': sadrzaj or [],
            'usage': dict({'input_tokens': 1, 'output_tokens': izlaz, 'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 7,
                           'cache_creation': {'ephemeral_5m_input_tokens': 7, 'ephemeral_1h_input_tokens': 0}}, **u)}}


def korisnik(t, tekst, uuid, **dodatno):
    return dict({'type': 'user', 'timestamp': t, 'uuid': uuid, 'message': {'role': 'user', 'content': tekst}}, **dodatno)


def izmena(ime, fajl, id_):
    return [{'type': 'tool_use', 'id': id_, 'name': ime, 'input': {'file_path': fajl}}]


class Izvestaj(Osnova):
    def pokreni(self, *dodatno):
        izlaz = os.path.join(self.tmp, 'izlaz')
        r = subprocess.run([sys.executable, os.path.join(KOREN, 'scripts', 'izvestaj_faza.py'), '--projekat', self.projekat,
                            '--transkripti', os.path.join(self.tmp, 't'), '--izlaz', izlaz, *dodatno],
                           capture_output=True, env={k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'})
        self.assertEqual(r.returncode, 0, r.stderr.decode('utf-8', 'replace'))
        with open(os.path.join(izlaz, 'izvestaj_faza.json'), encoding='utf-8') as j, open(os.path.join(izlaz, 'izvestaj_faza.md'), encoding='utf-8') as m:
            return json.load(j), m.read()

    def scenario(self):
        os.makedirs(self.usage)
        with open(os.path.join(self.usage, 'faze.jsonl'), 'w', encoding='utf-8') as f:
            for t, ime in (('2026-01-01T10:00:00+00:00', 'planiranje'), ('2026-01-01T11:00:00+00:00', 'implementacija'),
                           ('2026-01-01T12:00:00+00:00', 'kontrolni skup'), ('2026-01-01T13:00:00+00:00', 'implementacija')):
                f.write(json.dumps({'vreme': t, 'faza': ime}) + '\n')
        self.transkript('s1', [
            korisnik('2026-01-01T10:10:00.000Z', 'napravi plan', 'u1'),
            # isti message id u dva reda: drugi red nosi konacan broj izlaznih tokena
            poruka('m1', '2026-01-01T10:10:30.000Z', izlaz=2),
            poruka('m1', '2026-01-01T10:10:31.000Z', izlaz=50),
            korisnik('2026-01-01T10:20:00.000Z', [{'type': 'tool_result', 'tool_use_id': 'x', 'content': 'ok'}], 'u2'),
            korisnik('2026-01-01T10:30:00.000Z', 'hook poruka', 'u3', isMeta=True),
            poruka('m2', '2026-01-01T11:30:00.000Z', model='claude-opus-5-5', sadrzaj=izmena('Edit', 'C:\\p\\a.py', 't1')),
        ])
        self.transkript('s1', [
            korisnik('2026-01-01T11:31:00.000Z', 'zadatak agentu', 'a1'),
            poruka('m3', '2026-01-01T11:31:20.000Z', sadrzaj=izmena('Edit', 'C:\\p\\a.py', 't2')),
            poruka('m4', '2026-01-01T11:31:40.000Z', sadrzaj=izmena('Edit', 'C:\\p\\b.py', 't3')),
            korisnik('2026-01-01T11:31:41.000Z', [{'type': 'tool_result', 'tool_use_id': 't3', 'is_error': True, 'content': 'odbijeno'}], 'a2'),
        ], podagent='ag1')
        with open(os.path.join(self.tmp, 't', 's1', 'subagents', 'agent-ag1.meta.json'), 'w') as f:
            json.dump({'agentType': 'diplomski:qa'}, f)
        # nastavljena sesija kopira istoriju: m1 i u1 ne smeju da se broje dvaput
        self.transkript('s2', [
            korisnik('2026-01-01T10:10:00.000Z', 'napravi plan', 'u1'),
            poruka('m1', '2026-01-01T10:10:31.000Z', izlaz=50),
            korisnik('2026-01-01T13:10:00.000Z', 'popravi', 'u9'),
            poruka('m5', '2026-01-01T13:10:10.000Z', sadrzaj=izmena('Edit', 'C:\\p\\a.py', 't4')),
            korisnik('2026-01-01T13:10:11.000Z', [{'type': 'tool_result', 'tool_use_id': 't4', 'is_error': True, 'content': 'odbijeno'}], 'u10'),
        ])

    def test_brojke_faze_agenti(self):
        self.scenario()
        d, md = self.pokreni()
        faze = {r['faza']: r for r in d['po_fazi']}
        self.assertEqual(faze['planiranje']['izlaz'], 50)        # m1 jednom, konacan red
        self.assertEqual(faze['planiranje']['upita'], 1)         # meta i tool_result nisu upiti
        self.assertEqual(faze['planiranje']['trajanje_s'], 30.0)
        self.assertEqual(faze['implementacija']['poruka'], 4)    # m2, m3, m4, m5
        self.assertEqual(faze['implementacija']['upita'], 1)
        agenti = {r['agent']: r for r in d['po_agentu']}
        self.assertEqual(agenti['qa']['pokretanja'], 1)
        self.assertEqual(agenti['qa']['trajanje_s'], 40.0)
        self.assertEqual(agenti['glavna sesija']['pokretanja'], 2)
        self.assertEqual(agenti['glavna sesija']['upita'], 2)
        self.assertEqual({r['model'] for r in d['po_modelu']}, {'claude-haiku-5-5', 'claude-opus-5-5'})
        self.assertEqual(d['statistika']['duplikata'], 2)
        self.assertEqual(d['zidno_s_po_fazi']['planiranje'], 3600.0)

    def test_vracanja_i_tudje_izmene(self):
        self.scenario()
        d, _ = self.pokreni()
        self.assertEqual(d['vracanja_na_doradu'], 1)
        # a.py: s1 pa ag1 = 1; pokusaj iz s2 je odbijen i ne racuna se
        self.assertEqual(d['tudje_izmene_po_fazi'], {'implementacija': 1})

    def test_null_cene_daju_tokene_i_poruku(self):
        self.scenario()
        put = os.path.join(self.tmp, 'null.json')
        with open(put, 'w') as f:
            json.dump({'izvor': None, 'modeli': {}}, f)
        d, md = self.pokreni('--cene', put)
        self.assertTrue(all(r['cena_usd'] is None for r in d['po_fazi']))
        self.assertIn('cena nije podesena', md)
        self.assertTrue(sum(r['izlaz'] for r in d['po_fazi']) > 0)

    def test_cene_bez_izvora_se_ne_koriste_a_sa_izvorom_racunaju(self):
        self.scenario()
        cene = {'modeli': {m: {'ulaz': 1, 'izlaz': 2, 'cache_citanje': 0, 'cache_upis_5m': 0, 'cache_upis_1h': 0}
                           for m in ('claude-haiku-5-5', 'claude-opus-5-5')}}
        put = os.path.join(self.tmp, 'c.json')
        with open(put, 'w') as f:
            json.dump(dict(cene, izvor=None), f)
        self.assertIsNone(self.pokreni('--cene', put)[0]['po_fazi'][0]['cena_usd'])
        with open(put, 'w') as f:
            json.dump(dict(cene, izvor='https://primer'), f)
        d = self.pokreni('--cene', put)[0]
        plan = [r for r in d['po_fazi'] if r['faza'] == 'planiranje'][0]
        self.assertAlmostEqual(plan['cena_usd'], (1 * 1 + 50 * 2) / 1e6)

    def test_pre_prve_faze_ide_u_bez_faze(self):
        self.transkript('s1', [korisnik('2026-01-01T10:00:00.000Z', 'x', 'u1'), poruka('m1', '2026-01-01T10:00:05.000Z')])
        d, md = self.pokreni()
        self.assertEqual(d['po_fazi'][0]['faza'], '(bez faze)')
        self.assertIn('Nijedna faza nije upisana', md)

    def test_kontekst_ekstenzije_nije_rec_coveka(self):
        kontekst = '<ide_opened_file>Korisnik je otvorio a.py</ide_opened_file>'
        self.transkript('s1', [
            korisnik('2026-01-01T10:00:00.000Z', [{'type': 'text', 'text': kontekst}, {'type': 'text', 'text': 'napravi plan'}], 'u1'),
            poruka('m1', '2026-01-01T10:00:05.000Z'),
            korisnik('2026-01-01T10:00:06.000Z', [{'type': 'text', 'text': kontekst}], 'u2'),
            poruka('m2', '2026-01-01T10:00:09.000Z')])
        d, _ = self.pokreni()
        self.assertEqual([r['tekst'].strip() for r in d['po_upitu']], ['napravi plan'])
        self.assertEqual(d['ukupno']['upita_coveka'], 1)

    def test_razmak_preko_praga_se_ne_broji(self):
        self.transkript('s1', [korisnik('2026-01-01T10:00:00.000Z', 'x', 'u1'), poruka('m1', '2026-01-01T10:00:05.000Z'),
                               poruka('m2', '2026-01-01T14:00:05.000Z')])
        self.assertEqual(self.pokreni()[0]['po_agentu'][0]['trajanje_s'], 5.0)

    def test_podpitanja_i_rad_bez_cekanja_coveka(self):
        pitanje = [{'type': 'tool_use', 'id': 'q1', 'name': 'AskUserQuestion', 'input': {'questions': [{'question': 'a'}, {'question': 'b'}]}}]
        self.transkript('s1', [
            korisnik('2026-01-01T10:00:00.000Z', 'napravi', 'u1'),
            poruka('m1', '2026-01-01T10:00:10.000Z', sadrzaj=pitanje),
            korisnik('2026-01-01T10:05:10.000Z', [{'type': 'tool_result', 'tool_use_id': 'q1', 'content': 'odgovor'}], 'u2'),
            poruka('m2', '2026-01-01T10:05:20.000Z'),
            korisnik('2026-01-01T10:30:00.000Z', 'nastavi', 'u3'),
            poruka('m3', '2026-01-01T10:30:30.000Z'),
        ])
        d, md = self.pokreni()
        u = d['ukupno']
        self.assertEqual((u['upita_coveka'], u['dodatnih_upita'], u['pitanja_alatom'], u['podpitanja_coveku']), (2, 1, 2, 3))
        self.assertEqual((u['zidno_s'], u['rad_s'], u['cekanje_coveka_s']), (1830.0, 50.0, 1780.0))
        self.assertEqual([r['trajanje_s'] for r in d['po_upitu']], [320.0, 30.0])
        self.assertEqual([r['cekanje_s'] for r in d['po_upitu']], [300.0, 0.0])
        self.assertEqual([r['tekst'] for r in d['po_upitu']], ['napravi', 'nastavi'])
        self.assertEqual([r['poruka'] for r in d['po_upitu']], [2, 1])
        self.assertIn('Po upitu coveka', md)

    def test_haiku_iznad_praga_placa_skuplje(self):
        self.transkript('s1', [korisnik('2026-01-01T10:00:00.000Z', 'x', 'u1'),
                               poruka('m1', '2026-01-01T10:00:05.000Z', izlaz=0, cache_read_input_tokens=0, cache_creation_input_tokens=0, cache_creation={}),
                               poruka('m2', '2026-01-01T10:00:09.000Z', izlaz=0, cache_read_input_tokens=200000, cache_creation_input_tokens=0, cache_creation={})])
        nula = {'izlaz': 0, 'cache_citanje': 0, 'cache_upis_5m': 0, 'cache_upis_1h': 0}
        put = os.path.join(self.tmp, 'c.json')
        with open(put, 'w') as f:
            json.dump({'izvor': 'https://primer', 'modeli': {'claude-haiku-5-5': dict(nula, ulaz=1, prag_prompta=100000, iznad_praga=dict(nula, ulaz=10))}}, f)
        d, _ = self.pokreni('--cene', put)
        self.assertAlmostEqual(d['ukupno']['cena_usd'], (1 + 10) / 1e6)

    def test_prazan_claude_code_bez_markera_uz_transkripte(self):
        self.transkript('s1', [korisnik('2026-01-01T10:00:00.000Z', 'x', 'u1'), poruka('m1', '2026-01-01T10:00:05.000Z')])
        izlaz = os.path.join(self.tmp, 'iz')
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        skripta = os.path.join(KOREN, 'scripts', 'izvestaj_faza.py')
        bez_transkripata = subprocess.run([sys.executable, skripta, '--projekat', self.bez], capture_output=True, env=env)
        self.assertEqual(bez_transkripata.returncode, 2)
        r = subprocess.run([sys.executable, skripta, '--projekat', self.bez, '--transkripti', os.path.join(self.tmp, 't'), '--izlaz', izlaz], capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(izlaz, 'izvestaj_faza.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['ukupno']['poruka'], 1)
        self.assertEqual(os.listdir(self.bez), [])

    def test_stvarne_cene_su_iz_tabele_1_rada(self):
        with open(os.path.join(KOREN, 'scripts', 'cene.json'), encoding='utf-8') as f:
            c = json.load(f)
        self.assertTrue(c['izvor'] and c['provereno'])
        for model, ocekivano in (('claude-fable-5-1', (10, 50, 0.25)), ('claude-opus-5-5', (4, 20, 0.2)),
                                 ('claude-sonnet-5-5', (2, 10, 0.1)), ('claude-haiku-5-5', (0.1, 0.5, 0.01))):
            m = c['modeli'][model]
            self.assertEqual((m['ulaz'], m['izlaz'], m['cache_citanje']), ocekivano, model)


class Zaglavlja(unittest.TestCase):
    def test_svaki_skill_iz_zaglavlja_agenta_postoji(self):
        postoje = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(KOREN, 'skills', '*', '*', 'SKILL.md'))}
        agenti = glob.glob(os.path.join(KOREN, 'agents', '*.md'))
        self.assertEqual(len(agenti), 14)
        for put in agenti:
            with open(put, encoding='utf-8') as f:
                red = next(r for r in f if r.startswith('skills:'))
            for ime in red[len('skills:'):].split(','):
                self.assertIn(ime.strip(), postoje, os.path.basename(put))


class NoviProjekat(Osnova):
    def napravi(self, put):
        return subprocess.run([sys.executable, os.path.join(KOREN, 'scripts', 'novi_projekat.py'), put], capture_output=True)

    def test_prazan_folder(self):
        cilj = os.path.join(self.tmp, 'novi')
        self.assertEqual(self.napravi(cilj).returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(cilj, '.claude', 'diplomski-projekat')))
        self.assertTrue(os.path.isfile(os.path.join(cilj, '.claude', 'skills', 'projekat-domen', 'SKILL.md')))
        self.assertTrue(os.path.isfile(os.path.join(cilj, '.claude', 'skills', 'projekat-domen', 'references', 'parametri.md')))
        self.assertTrue(os.path.isfile(os.path.join(cilj, 'CLAUDE.md')))
        with open(os.path.join(cilj, '.claude', 'settings.json')) as f:
            self.assertEqual(json.load(f)['enabledPlugins'], {'diplomski@skills-dir': True, 'brain@skills-dir': False})

    def test_putanje_su_stvarna_lokacija_plugina(self):
        cilj = os.path.join(self.tmp, 'novi')
        self.assertEqual(self.napravi(cilj).returncode, 0)
        with open(os.path.join(cilj, 'CLAUDE.md'), encoding='utf-8') as f:
            tekst = f.read()
        self.assertIn(KOREN.replace('\\', '/') + '/scripts/faza.py', tekst)
        self.assertNotIn('<plugin>', tekst)
        self.assertIn('craft-delegiranje', tekst)
        with open(os.path.join(cilj, '.claude', 'settings.json')) as f:
            pravilo = json.load(f)['permissions']['allow'][0]
        self.assertTrue(pravilo.startswith('Read(//') and pravilo.endswith('/**)'), pravilo)
        self.assertIn('diplomski', pravilo)

    def test_neprazan_odbijen_i_netaknut(self):
        with open(os.path.join(self.bez, 'x.txt'), 'w') as f:
            f.write('x')
        self.assertEqual(self.napravi(self.bez).returncode, 2)
        self.assertEqual(os.listdir(self.bez), ['x.txt'])

    def test_unutar_repoa_odbijen(self):
        cilj = os.path.join(KOREN, 'aplikacija-proba')
        self.assertEqual(self.napravi(cilj).returncode, 2)
        self.assertFalse(os.path.exists(cilj))


class Budzet(Osnova):
    SKRIPTA = os.path.join(KOREN, 'scripts', 'budget.py')

    def test_repo_prolazi_i_ispisuje_trosak_poziva(self):
        r = subprocess.run([sys.executable, self.SKRIPTA, '--strict'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('Trosak poziva agenta', r.stdout)
        self.assertRegex(r.stdout, r'\bqa\s+\d+ znakova')

    def test_kratak_opis_skilla_pada(self):
        os.makedirs(os.path.join(self.bez, 'scripts'))
        os.makedirs(os.path.join(self.bez, 'skills', 'sloj', 'mali'))
        shutil.copy(self.SKRIPTA, os.path.join(self.bez, 'scripts'))
        with open(os.path.join(self.bez, 'skills', 'sloj', 'mali', 'SKILL.md'), 'w') as f:
            f.write('---\nname: mali\ndescription: kratko\n---\n')
        r = subprocess.run([sys.executable, os.path.join(self.bez, 'scripts', 'budget.py'), '--strict'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('opis 6 znakova', r.stdout)


class Evaluacije(unittest.TestCase):
    def test_svi_slucajevi_prolaze_i_nose_poreklo(self):
        r = subprocess.run([sys.executable, os.path.join(KOREN, 'scripts', 'evals.py')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(os.path.join(KOREN, 'scripts', 'evals.json'), encoding='utf-8') as f:
            slucajevi = json.load(f)
        self.assertGreaterEqual(len(slucajevi), 11)
        self.assertTrue(all(s['poreklo'] for s in slucajevi))

    def test_evaluacija_koristi_tacan_pocetni_upit(self):
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import priprema_poredjenja
        with open(os.path.join(KOREN, 'scripts', 'evals.json'), encoding='utf-8') as f:
            upiti = [s['upit'] for s in json.load(f)]
        self.assertIn(priprema_poredjenja.UPIT, upiti)
        self.assertIn(priprema_poredjenja.UPIT_STIL, upiti)


class Mvp(unittest.TestCase):
    ZAGLAVLJA = ('Krug', 'Tezina', 'Model', 'Nivo', 'Kontekst', 'Podela')

    @staticmethod
    def redovi(tekst):
        izlaz = {}
        for r in tekst.split('\n'):
            if r.startswith('|') and '---' not in r:
                celije = [c.strip() for c in r.strip('|').split('|')]
                izlaz.setdefault(celije[0], []).append(celije[1:])
        return izlaz

    def razlike(self, deo, specifikacija):
        brojevi = lambda celije: set(re.findall(r'[-+]?\d[\d.,]*', ' '.join(celije)))
        spec = self.redovi(specifikacija)
        return [k for k, nizovi in self.redovi(deo).items() if k not in self.ZAGLAVLJA
                for red in nizovi if not any(brojevi(red) <= brojevi(p) for p in spec.get(k, []))]

    def test_brojevi_u_mvp_su_isti_kao_u_specifikaciji_igre(self):
        with open(os.path.join(KOREN, 'MVP-orkestrator.md'), encoding='utf-8') as f:
            deo = f.read().split('## 5. Parametri')[1].split('## 6.')[0]
        with open(os.path.join(KOREN, 'skills', 'sloj-projekta', 'projekat-domen', 'references', 'parametri.md'), encoding='utf-8') as f:
            specifikacija = f.read()
        self.assertEqual(sum(len(v) for k, v in self.redovi(deo).items() if k not in self.ZAGLAVLJA), 23)
        self.assertEqual(self.razlike(deo, specifikacija), [])
        self.assertEqual(self.razlike(deo.replace('7,20', '7,30'), specifikacija), ['Opus'])   # provera mora da moze da padne
        for red in ('Budzet **24 $**', 'rok **150 min**'):
            self.assertIn(red, deo)
            self.assertIn(red, specifikacija)


class Poredjenje(Osnova):
    PRIPREMA = os.path.join(KOREN, 'scripts', 'priprema_poredjenja.py')
    POREDJENJE = os.path.join(KOREN, 'scripts', 'poredjenje.py')

    def setUp(self):
        super().setUp()
        self.koren = os.path.join(self.tmp, 'poredjenje')

    def pripremi(self, koren=None, *dodatno):
        return subprocess.run([sys.executable, self.PRIPREMA, koren or self.koren, *(dodatno or ('--bez-venv',))], capture_output=True, text=True, encoding='utf-8')

    INIT_PRAZAN = {'permissionMode': 'acceptEdits', 'tools': ['Bash', 'Edit', 'Read'], 'skills': [], 'slash_commands': [], 'mcp_servers': [],
                   'agents': ['Explore', 'Plan', 'general-purpose'], 'plugins': [{'name': 'x', 'source': 'cc-plugin-x@builtin'}]}
    INIT_PLUGIN = {'permissionMode': 'acceptEdits', 'tools': ['Bash', 'Task', 'Skill'], 'mcp_servers': [], 'agents': ['Explore', 'diplomski:planer'],
                   'skills': ['diplomski:craft-code', 'diplomski:craft-delegiranje', 'projekat-domen', 'projekat-standardi', 'projekat-odluke'],
                   'slash_commands': ['diplomski:craft-code'], 'plugins': [{'source': 'diplomski@skills-dir'}, {'source': 'cc-plugin-x@builtin'}]}

    def modul_poredjenja(self):
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import poredjenje
        return poredjenje

    def test_cista_prazna_sesija_nema_problema_a_svako_curenje_se_prijavljuje(self):
        problemi = self.modul_poredjenja().problemi_sesije
        self.assertEqual(problemi('prazan', self.INIT_PRAZAN), [])
        for izmena, ocekivano in (({'tools': ['Bash', 'Task']}, 'dostupni alati'), ({'tools': ['Bash', 'Workflow']}, 'dostupni alati'), ({'skills': ['simplify']}, 'ima skillove'),
                                  ({'agents': ['planer']}, 'dodatni agenti'), ({'permissionMode': 'bypassPermissions'}, 'rezim dozvola'),
                                  ({'plugins': [{'source': 'diplomski@skills-dir'}]}, 'dodatni pluginovi'), ({'mcp_servers': [{'name': 'aws'}]}, 'MCP'),
                                  ({'agents': ['brain:scout']}, 'brain')):
            self.assertTrue(any(ocekivano in p for p in problemi('prazan', dict(self.INIT_PRAZAN, **izmena))), ocekivano)

    def test_plugin_sesija_mora_da_ima_plugin_skillove_i_agente(self):
        problemi = self.modul_poredjenja().problemi_sesije
        self.assertEqual(problemi('plugin', self.INIT_PLUGIN), [])
        for izmena, ocekivano in (({'skills': self.INIT_PLUGIN['skills'] + ['anthropic-skills:pdf']}, 'skillovi naloga'), ({'plugins': []}, 'plugin diplomski'), ({'skills': []}, 'nedostaje skill'), ({'agents': []}, 'agent planer'), ({'tools': ['Bash']}, 'Task')):
            self.assertTrue(any(ocekivano in p for p in problemi('plugin', dict(self.INIT_PLUGIN, **izmena))), ocekivano)

    def test_svaka_strana_ima_svoj_cursor_i_ogranicenja_u_podesavanjima(self):
        self.assertEqual(self.pripremi().returncode, 0)
        with open(os.path.join(self.koren, 'prazan', 'config', 'settings.json'), encoding='utf-8') as f:
            prazan = json.load(f)
        with open(os.path.join(self.koren, 'plugin', 'config', 'settings.json'), encoding='utf-8') as f:
            plugin = json.load(f)
        for alat in ('Agent', 'Task', 'Skill', 'Workflow'):
            self.assertIn(alat, prazan['permissions']['deny'])
        self.assertTrue(prazan['disableBundledSkills'])
        self.assertNotIn('deny', plugin['permissions'])
        self.assertNotIn('disableBundledSkills', plugin)
        for strana, podesavanja in (('prazan', prazan), ('plugin', plugin)):
            self.assertEqual(podesavanja['permissions']['defaultMode'], 'acceptEdits')
            self.assertEqual((podesavanja['model'], podesavanja['effortLevel'], podesavanja['syncClaudeAiSkills']), ('opus', 'high', False))
            config = os.path.join(self.koren, strana, 'config')
            with open(os.path.join(self.koren, strana, 'otvori.cmd'), encoding='utf-8') as f:
                otvori = f.read()
            self.assertIn('CLAUDE_CONFIG_DIR=' + config, otvori)
            self.assertIn('--new-window "%s"' % self.projekat_strane(strana), otvori)
            self.assertNotIn('--user-data-dir', otvori)                    # poseban profil trazi novu prijavu u Cursor-u
            self.assertIn('set CLAUDE', otvori)
            self.assertIn('set "PWD="', otvori)
        with open(os.path.join(self.koren, 'POKRETANJE.md'), encoding='utf-8') as f:
            tekst = f.read()
        self.assertNotIn('bypassPermissions', tekst)
        self.assertIn('otvori.cmd', tekst)
        self.assertNotIn('pokreni.cmd', tekst)

    def test_trag_prijavljuje_stranu_bez_transkripta(self):
        self.pripremljena_izrada()
        self.assertEqual(self.komanda('trag').returncode, 0)
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import izvestaj_faza
        os.remove(os.path.join(self.koren, 'plugin', 'config', 'projects', izvestaj_faza.slug(self.projekat_strane('plugin')), 's.jsonl'))
        r = self.komanda('trag')
        self.assertEqual(r.returncode, 1)
        self.assertIn('NIJE ISPRAVNO', r.stdout)

    def test_venv_nastaje_po_strani_i_vidi_sistemske_pakete(self):
        self.assertEqual(self.pripremi(self.koren, '--bez-provere-ne-postoji').returncode, 2)   # nepoznata opcija ne prolazi tiho
        r = subprocess.run([sys.executable, self.PRIPREMA, self.koren], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        for strana in ('prazan', 'plugin'):
            with open(os.path.join(self.koren, strana, 'venv', 'pyvenv.cfg'), encoding='utf-8') as f:
                self.assertIn('include-system-site-packages = true', f.read())

    def test_folder_prazne_strane_sa_viskom_se_prijavljuje(self):
        self.assertEqual(self.pripremi().returncode, 0)
        modul = self.modul_poredjenja().problemi_foldera
        # privremeni folder moze biti pod home-om, a tamo je ~/.claude: gleda se samo ono sto je test napravio
        problemi = lambda koren, strana: [p for p in modul(koren, strana) if 'roditelj ima' not in p or koren in p]
        for s in ('prazan', 'plugin'):
            self.assertEqual(problemi(self.koren, s), [], s)
        with open(os.path.join(self.projekat_strane('prazan'), 'CLAUDE.md'), 'w') as f:
            f.write('x')
        sinhronizovan = os.path.join(self.koren, 'prazan', 'config', 'skills', 'synced', 'nalog', 'pdf')
        sklonjen = os.path.join(self.koren, 'prazan', 'config', 'skills', '.trash', 'x')
        for folder in (sinhronizovan, sklonjen):
            os.makedirs(folder)
            open(os.path.join(folder, 'SKILL.md'), 'w').close()
        with open(os.path.join(self.koren, 'CLAUDE.md'), 'w') as f:
            f.write('x')
        p = ' | '.join(problemi(self.koren, 'prazan'))
        for ocekivano in ('nije samo MVP.md', 'ima 1 skillova van sistema', 'roditelj ima'):
            self.assertIn(ocekivano, p)
        with open(os.path.join(self.koren, 'prazan', 'config', 'settings.json'), 'w') as f:
            json.dump({'syncClaudeAiSkills': True}, f)
        self.assertIn('nije propisan', ' | '.join(problemi(self.koren, 'prazan')))
        projekti = os.path.join(self.koren, 'plugin', 'config', 'projects', 'x')
        os.makedirs(projekti)
        with open(os.path.join(projekti, 's.jsonl'), 'w') as f:
            f.write('{}')
        os.makedirs(os.path.join(self.koren, 'plugin', 'config', 'plugins'))
        with open(os.path.join(self.koren, 'plugin', 'config', 'plugins', 'installed_plugins.json'), 'w') as f:
            json.dump({'plugins': {'brain': []}}, f)
        p = ' | '.join(problemi(self.koren, 'plugin'))
        self.assertIn('vec postoji transkript', p)
        self.assertIn('dodatni pluginovi', p)
        self.assertNotIn('config ima plugins', p)

    def komanda(self, ime):
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        return subprocess.run([sys.executable, self.POREDJENJE, ime, self.koren], capture_output=True, text=True, encoding='utf-8', env=env)

    def projekat_strane(self, strana):
        return os.path.join(self.koren, strana, 'projekat')

    def zapis_izrade(self, strana, izlaz, test_prolazi):
        projekat = self.projekat_strane(strana)
        with open(os.path.join(projekat, 'manage.py'), 'w') as f:
            f.write(TestSummary.MANAGE)
        with open(os.path.join(projekat, 't_a.py'), 'w') as f:
            f.write(TestSummary.TEST % (1 if test_prolazi else 2))
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import izvestaj_faza
        folder = os.path.join(self.koren, strana, 'config', 'projects', izvestaj_faza.slug(projekat))
        os.makedirs(folder)
        with open(os.path.join(folder, 's.jsonl'), 'w', encoding='utf-8') as f:
            for r in (korisnik('2026-01-01T10:00:00.000Z', 'x', 'u1'), poruka('m1', '2026-01-01T10:01:00.000Z', model='claude-opus-5-5', izlaz=izlaz)):
                f.write(json.dumps(r) + '\n')

    def test_priprema_daje_isti_mvp_bez_tragova_plugina(self):
        r = self.pripremi()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.projekat_strane('prazan'), 'MVP.md'), 'rb') as f:
            prazan = f.read()
        with open(os.path.join(self.projekat_strane('plugin'), 'MVP.md'), 'rb') as f:
            self.assertEqual(prazan, f.read())
        tekst = prazan.decode('utf-8')
        for mora in ('8 krugova', 'Budzet **24 $**', 'Kada je gotovo', 'Test balansa', 'slobodan port'):
            self.assertIn(mora, tekst)
        for ne_sme in ('CLAUDE_PLUGIN_ROOT', 'references/', 'projekat-', 'stack-django', 'skill', 'plugin', 'motor.py'):
            self.assertNotIn(ne_sme, tekst)

    def test_prazna_strana_nema_nista_od_plugina_a_plugin_strana_ima(self):
        self.assertEqual(self.pripremi().returncode, 0)
        self.assertEqual(os.listdir(self.projekat_strane('prazan')), ['MVP.md'])
        self.assertEqual(os.listdir(os.path.join(self.koren, 'prazan', 'config')), ['settings.json'])
        snimak = os.path.join(self.koren, 'plugin', 'config', 'skills', 'diplomski')
        self.assertTrue(os.path.isfile(os.path.join(snimak, '.claude-plugin', 'plugin.json')))
        self.assertFalse(os.path.exists(os.path.join(snimak, '.git')))
        self.assertFalse(os.path.exists(os.path.join(snimak, 'MVP-orkestrator.md')))
        self.assertEqual(glob.glob(os.path.join(snimak, '*.pdf')) + glob.glob(os.path.join(snimak, '*.docx')), [])
        self.assertTrue(os.path.isfile(os.path.join(self.projekat_strane('plugin'), '.claude', 'diplomski-projekat')))
        with open(os.path.join(self.projekat_strane('plugin'), 'CLAUDE.md'), encoding='utf-8') as f:
            self.assertIn(snimak.replace('\\', '/') + '/scripts/faza.py', f.read())

    def test_manifest_i_upit(self):
        self.assertEqual(self.pripremi().returncode, 0)
        with open(os.path.join(self.koren, 'manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        self.assertEqual(len(m['upiti']), 13)
        for ime, tekst in m['upiti'].items():
            with open(os.path.join(self.koren, ime), encoding='utf-8') as f:
                self.assertEqual(f.read().strip(), tekst, ime)
        for ne_sme in ('test', 'bezbed', 'telefon', '375', 'xss', 'mnozin', 'migraci', 'csrf', 'debug', 'napad'):
            for ime in ('UPIT-4-rang.txt', 'UPIT-5-deljenje.txt', 'UPIT-6-jezik.txt', 'UPIT-7-bodovanje.txt',
                        'UPIT-8-moderator.txt', 'UPIT-9-javno.txt', 'UPIT-10-izazov.txt', 'UPIT-11-csv.txt', 'UPIT-12-prijava.txt', 'UPIT-13-pet.txt'):
                self.assertNotIn(ne_sme, m['upiti'][ime].lower(), ime)   # provere kvaliteta su posao skillova, ne upita
        self.assertEqual(len(m['mvp_sha256']), 64)
        self.assertTrue(m['plugin']['commit'])

    def test_neprazan_i_unutar_gita_odbijeni(self):
        with open(os.path.join(self.bez, 'x'), 'w') as f:
            f.write('x')
        self.assertEqual(self.pripremi(self.bez).returncode, 2)
        self.assertEqual(os.listdir(self.bez), ['x'])
        repo = os.path.join(self.tmp, 'repo')
        os.makedirs(repo)
        subprocess.run(['git', 'init', '-q', repo], check=True)
        cilj = os.path.join(repo, 'pod', 'poredjenje')
        self.assertEqual(self.pripremi(cilj).returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(repo, 'pod')))

    def pripremljena_izrada(self):
        self.assertEqual(self.pripremi().returncode, 0)
        self.zapis_izrade('prazan', 100, True)
        self.zapis_izrade('plugin', 40, False)

    def test_slepa_kopija_ne_otkriva_stranu_i_ne_prepisuje_ocene(self):
        self.pripremljena_izrada()
        self.assertEqual(self.komanda('slepo').returncode, 0)
        ocena = os.path.join(self.koren, 'ocena')
        with open(os.path.join(ocena, 'kljuc.json')) as f:
            self.assertEqual(sorted(json.load(f).values()), ['plugin', 'prazan'])
        for oznaka in ('X', 'Y'):
            self.assertIn('manage.py', os.listdir(os.path.join(ocena, oznaka)))
            self.assertNotIn('.claude', os.listdir(os.path.join(ocena, oznaka)))
            self.assertNotIn('CLAUDE.md', os.listdir(os.path.join(ocena, oznaka)))
        self.assertEqual(self.komanda('slepo').returncode, 2)

    def test_izvestaj_spaja_merenje_testove_i_ocenu_po_kljucu(self):
        self.pripremljena_izrada()
        self.assertEqual(self.komanda('slepo').returncode, 0)
        put = os.path.join(self.koren, 'ocena', 'ocena.json')
        with open(put, encoding='utf-8') as f:
            obrazac = json.load(f)
        for v in obrazac['ocene'].values():
            v.update(X=5, Y=3)
        with open(put, 'w', encoding='utf-8') as f:
            json.dump(obrazac, f, ensure_ascii=False)
        r = self.komanda('izvestaj')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.koren, 'rezultati', 'poredjenje.json'), encoding='utf-8') as f:
            d = json.load(f)['strane']
        with open(os.path.join(self.koren, 'ocena', 'kljuc.json')) as f:
            kljuc = json.load(f)
        self.assertEqual(d[kljuc['X']]['ocena']['prosek'], 5.0)
        self.assertEqual(d[kljuc['Y']]['ocena']['prosek'], 3.0)
        self.assertEqual((d['prazan']['ukupno']['izlaz'], d['plugin']['ukupno']['izlaz']), (100, 40))
        self.assertAlmostEqual(d['prazan']['ukupno']['cena_usd'], (1 * 4 + 100 * 20 + 100 * 0.2 + 7 * 5) / 1e6)
        self.assertEqual((d['prazan']['testovi']['exit'], d['prazan']['testovi']['palo']), (0, 0))
        self.assertEqual((d['plugin']['testovi']['exit'], d['plugin']['testovi']['palo']), (1, 1))
        self.assertTrue(os.path.exists(os.path.join(self.koren, 'rezultati', 'poredjenje.md')))
        self.assertEqual(d['prazan']['cistoca']['pozivi_agenata_i_skillova'], 0)

    def test_poziv_agenta_na_praznoj_strani_ponistava_merenje(self):
        self.pripremljena_izrada()
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import izvestaj_faza
        folder = os.path.join(self.koren, 'prazan', 'config', 'projects', izvestaj_faza.slug(self.projekat_strane('prazan')))
        agent = [{'type': 'tool_use', 'id': 'a1', 'name': 'Task', 'input': {}}]
        with open(os.path.join(folder, 's.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(poruka('m9', '2026-01-01T10:02:00.000Z', model='claude-opus-5-5', sadrzaj=agent)) + '\n')
        r = self.komanda('izvestaj')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.koren, 'rezultati', 'poredjenje.md'), encoding='utf-8') as f:
            self.assertIn('MERENJE NIJE VAZECE', f.read())

    def test_planiranje_i_izrada_odvojeno_a_potvrda_nije_podpitanje(self):
        self.assertEqual(self.pripremi().returncode, 0)
        sys.path.insert(0, os.path.join(KOREN, 'scripts'))
        import izvestaj_faza, priprema_poredjenja
        pitanje = [{'type': 'tool_use', 'id': 'q1', 'name': 'AskUserQuestion', 'input': {'questions': [{'question': 'a'}]}}]
        for strana, redovi in (('prazan', [
                korisnik('2026-01-01T10:00:00.000Z', priprema_poredjenja.UPIT, 'u1'),
                poruka('m1', '2026-01-01T10:00:10.000Z', model='claude-opus-5-5', sadrzaj=pitanje),
                korisnik('2026-01-01T10:10:10.000Z', [{'type': 'tool_result', 'tool_use_id': 'q1', 'content': 'x'}], 'u2'),
                poruka('m2', '2026-01-01T10:10:20.000Z', model='claude-opus-5-5'),
                korisnik('2026-01-01T11:00:00.000Z', priprema_poredjenja.UPIT_IZRADA, 'u3'),
                poruka('m3', '2026-01-01T11:00:40.000Z', model='claude-opus-5-5'),
                korisnik('2026-01-01T12:00:00.000Z', priprema_poredjenja.UPIT_STIL, 'u4'),
                poruka('m4', '2026-01-01T12:00:30.000Z', model='claude-opus-5-5')]),
                ('plugin', [korisnik('2026-01-01T10:00:00.000Z', priprema_poredjenja.UPIT, 'u1'),
                            poruka('m1', '2026-01-01T10:00:10.000Z', model='claude-opus-5-5')])):
            folder = os.path.join(self.koren, strana, 'config', 'projects', izvestaj_faza.slug(self.projekat_strane(strana)))
            os.makedirs(folder)
            with open(os.path.join(folder, 's.jsonl'), 'w', encoding='utf-8') as f:
                for r in redovi:
                    f.write(json.dumps(r) + '\n')
        r = self.komanda('izvestaj')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.koren, 'rezultati', 'poredjenje.json'), encoding='utf-8') as f:
            d = json.load(f)['strane']
        self.assertEqual(d['prazan']['planiranje']['trajanje_s'], 20.0)    # 620 s bez 600 s cekanja na odgovor
        self.assertEqual(d['prazan']['izrada']['trajanje_s'], 40.0)        # izrada staje gde pocinje stil
        self.assertEqual(d['prazan']['stil']['trajanje_s'], 30.0)
        self.assertGreater(d['prazan']['planiranje']['tokeni'], d['prazan']['izrada']['tokeni'])
        self.assertEqual(d['prazan']['podpitanja_coveku'], 1)              # pitanje alatom; propisani upiti se ne broje
        self.assertIsNone(d['plugin']['izrada'])                           # bez propisanog upita nema podele
        self.assertIsNone(d['plugin']['stil'])
        self.assertEqual(d['plugin']['podpitanja_coveku'], 0)

    def test_nepopunjena_ocena_ne_rusi_izvestaj_a_neispravna_pada(self):
        self.pripremljena_izrada()
        self.assertEqual(self.komanda('izvestaj').returncode, 0)
        with open(os.path.join(self.koren, 'rezultati', 'poredjenje.md'), encoding='utf-8') as f:
            self.assertIn('nije ocenjeno', f.read())
        self.assertEqual(self.komanda('slepo').returncode, 0)
        put = os.path.join(self.koren, 'ocena', 'ocena.json')
        with open(put, encoding='utf-8') as f:
            obrazac = json.load(f)
        for v in obrazac['ocene'].values():
            v.update(X=9, Y=3)
        with open(put, 'w', encoding='utf-8') as f:
            json.dump(obrazac, f, ensure_ascii=False)
        self.assertNotEqual(self.komanda('izvestaj').returncode, 0)


if __name__ == '__main__':
    unittest.main()
