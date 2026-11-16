# -*- coding: utf-8 -*-
"""Grafici za odbranu: rezultati poredjenja prazne sesije i plugina.

Brojevi su iz izvestaja `poredjenje.py izvestaj` i iz `Zapazanja iz poredjenja.docx` (odeljci 5-5.10.1).
Boje: referentna paleta skilla dataviz, provereni parovi (plava/narandzasta, akva/ljubicasta).

    python scripts/grafici_prezentacije.py [izlazni folder]
"""
import os, sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

IZLAZ = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join('prezentacija', 'slike', 'grafici'))
os.makedirs(IZLAZ, exist_ok=True)

POVRSINA, TEKST, TEKST2, MREZA = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
PRAZAN, PLUGIN = '#2a78d6', '#eb6834'          # slot 1 i 2
CENA, VREME = '#1baf7a', '#6250d6'             # slot 3 i 7: mere, ne strane
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 13, 'text.color': TEKST, 'axes.labelcolor': TEKST2,
    'xtick.color': TEKST2, 'ytick.color': TEKST2, 'axes.edgecolor': MREZA, 'figure.facecolor': POVRSINA,
    'axes.facecolor': POVRSINA, 'axes.titlesize': 18, 'axes.titleweight': 'bold', 'axes.titlelocation': 'left',
    'axes.spines.top': False, 'axes.spines.right': False, 'savefig.facecolor': POVRSINA,
})


def nova(sirina=16, visina=9):
    fig, ax = plt.subplots(figsize=(sirina / 1.6, visina / 1.6), dpi=200)
    ax.grid(axis='y', color=MREZA, linewidth=0.8); ax.set_axisbelow(True)
    return fig, ax


def naslov(fig, tekst):
    """Naslov preko cele slike, levo: naslov nad osom se sece kada su oznake ose siroke."""
    fig.suptitle(tekst, x=0.01, ha='left', fontsize=18, fontweight='bold')


def broj(x, decimala=1):
    """Decimalni zarez, kao u igri i u radu."""
    return ('%.*f' % (decimala, x)).replace('.', ',')


def sacuvaj(fig, ime, izvor):
    fig.text(0.01, 0.01, izvor, color=TEKST2, fontsize=9, va='bottom')
    fig.tight_layout(rect=(0, 0.05 if '\n' in izvor else 0.03, 1, 0.95))
    fig.savefig(os.path.join(IZLAZ, ime), dpi=200)
    plt.close(fig)
    print('grafik:', ime)


IZVOR = 'Извор: мерење из транскрипата, poredjenje.py izvestaj; цене по званичном ценовнику, 2026-11.'

# 1. cena po zahtevu
FAZE = [('план', '', .95, 3.05), ('израда', '', 1.93, 22.75), ('стил', '', 2.61, 14.22),
        ('ранг\nлиста', '', 2.46, 34.58), ('дељење', '', 1.71, 28.49), ('језик', '', 4.01, 43.74),
        ('бодо-\nвање', '', 1.48, 33.17), ('модера-\nтор', '', 4.05, 49.59), ('јавни\nрад', '', 3.85, 81.42),
        ('дневни\nизазов', 'v2\nSonnet', .49, 9.84), ('CSV', 'v2.2\nOpus low', .70, 2.48),
        ('пријава\nимена', 'v2.3\nFable max', 13.45, 33.56), ('5 зада-\nтака', 'v2.4\nOpus high', 6.05, 14.99)]
fig, ax = nova(18, 9)
x = range(len(FAZE)); w = 0.38
ax.axvspan(8.5, 12.5, color=MREZA, alpha=0.45, linewidth=0, zorder=0)
ax.bar([i - w / 2 for i in x], [f[2] for f in FAZE], w, color=PRAZAN, edgecolor=POVRSINA, linewidth=1.5, label='празна сесија', zorder=2)
ax.bar([i + w / 2 for i in x], [f[3] for f in FAZE], w, color=PLUGIN, edgecolor=POVRSINA, linewidth=1.5, label='плагин', zorder=2)
ax.set_xticks(list(x), [f[0] for f in FAZE], fontsize=10.5)
ax.set_ylabel('цена захтева ($)')
naslov(fig, 'Цена по захтеву: празна сесија и плагин')
for i, f in enumerate(FAZE):
    ax.text(i + w / 2, f[3] + 1, broj(f[3], 0) if f[3] >= 10 else broj(f[3]), ha='center', fontsize=9.5, color=TEKST2)
    if f[1]:
        ax.text(i, 60, f[1], ha='center', va='top', fontsize=9.5, color=TEKST2)
ax.text(4, 88, 'плагин v1 (тим агената), обе стране Opus', ha='center', color=TEKST2, fontsize=11)
ax.text(10.5, 88, 'после оптимизације плагина', ha='center', color=TEKST2, fontsize=11)
ax.set_ylim(0, 92)
ax.legend(frameon=False, loc='upper left', bbox_to_anchor=(0, 0.93))
sacuvaj(fig, '01-cena-po-zahtevu.png', IZVOR)

# 2. odnos plugin / prazan po verziji
VERZIJE = [('v1\nтим агената\n(Opus)', 13.5, 11.0), ('v2\nталаси\n(Sonnet)', 20.1, 26.4), ('v2.2\nлаки пут\n(Opus low)', 3.5, 5.9),
           ('v2.3\nбрзи тестови\n(Fable max)', 2.5, 2.3), ('v2.4\nпаралелни радници\n(Opus high)', 2.5, 3.2)]
fig, ax = nova(16, 9)
x = range(len(VERZIJE)); w = 0.36
for pomak, kolona, boja, oznaka in ((-w / 2, 1, CENA, 'цена'), (w / 2, 2, VREME, 'време рада')):
    ax.bar([i + pomak for i in x], [v[kolona] for v in VERZIJE], w, color=boja, edgecolor=POVRSINA, linewidth=1.5, label=oznaka)
    for i, v in enumerate(VERZIJE):
        ax.text(i + pomak, v[kolona] + 0.4, broj(v[kolona]) + '×', ha='center', fontsize=11, color=TEKST)
ax.axhline(1, color=TEKST2, linewidth=1.2, linestyle='--', label='празна сесија = 1×')
ax.set_xticks(list(x), [v[0] for v in VERZIJE], fontsize=11)
ax.set_ylabel('колико пута више од празне сесије')
naslov(fig, 'Плагин у односу на празну сесију, по верзији')
ax.legend(frameon=False, loc='upper right')
sacuvaj(fig, '02-odnos-po-verziji.png', IZVOR + ' v2.4: време са тестовима; без њих око 2,3×.')

# 3. nalazi nezavisne provere
NALAZI = [('средњи', 2, 0), ('низак', 2, 0), ('скривен', 1, 0)]
fig, ax = nova(14, 7)
ax.grid(axis='y', visible=False); ax.grid(axis='x', color=MREZA, linewidth=0.8)
y = range(len(NALAZI)); h = 0.36
ax.barh([i + h / 2 for i in y], [n[1] for n in NALAZI], h, color=PRAZAN, edgecolor=POVRSINA, linewidth=1.5, label='празна сесија')
ax.barh([i - h / 2 for i in y], [max(n[2], 0.02) for n in NALAZI], h, color=PLUGIN, edgecolor=POVRSINA, linewidth=1.5, label='плагин')
for i, n in enumerate(NALAZI):
    ax.text(n[1] + 0.05, i + h / 2, str(n[1]), va='center', fontsize=12)
    ax.text(0.08, i - h / 2, '0', va='center', fontsize=12)
ax.set_yticks(list(y), [n[0] for n in NALAZI]); ax.invert_yaxis()
ax.set_xlim(0, 3); ax.set_xticks([0, 1, 2, 3])
ax.set_xlabel('број пропуста које је нашла независна провера, 13 захтева')
naslov(fig, 'Пропусти које је нашла независна провера')
ax.legend(frameon=False, loc='lower right')
sacuvaj(fig, '03-nalazi-provere.png', 'Средњи: ограничење пријаве модератора, формула у Excel-у.\nНизак: невидљиво име, наслагани знакови. Скривен: српска множина.')

# 4. gde ide novac plugina v1
AGENTI = [('security', 77.54), ('qa', 75.50), ('backend-senior', 62.86), ('главна сесија', 31.29), ('devops', 29.31),
          ('planer', 23.76), ('остали (5 агената)', 10.77)]
fig, ax = nova(14, 8)
ax.grid(axis='y', visible=False); ax.grid(axis='x', color=MREZA, linewidth=0.8)
ax.barh(range(len(AGENTI)), [a[1] for a in AGENTI], 0.6, color=PLUGIN, edgecolor=POVRSINA, linewidth=1.5)
for i, a in enumerate(AGENTI):
    ax.text(a[1] + 1, i, broj(a[1], 0) + ' $', va='center', fontsize=12)
ax.set_yticks(range(len(AGENTI)), [a[0] for a in AGENTI]); ax.invert_yaxis()
ax.set_xlabel('цена ($), плагин v1, 9 захтева')
naslov(fig, 'Где одлази новац тима агената: контрола је половина')
sacuvaj(fig, '04-cena-po-agentu-v1.png', IZVOR)

# 5. runda 7: tok rada
TOK = [('празна сесија', [(0, 17.9, PRAZAN, 'један агент, Opus high')]),
       ('плагин: питања и мапа', [(0, 4.3, PLUGIN, '')]),
       ('радник: историја', [(4.3, 19.1, PLUGIN, '')]), ('радник: JSON', [(4.3, 7.1, PLUGIN, '')]),
       ('радник: статистика', [(4.3, 17.3, PLUGIN, '')]), ('радник: правила', [(8.2, 18.1, PLUGIN, '')]),
       ('радник: звук', [(8.2, 28.0, PLUGIN, '')]), ('спајање грана', [(28.5, 40.5, PLUGIN, 'од тога цео пакет 10 мин')]),
       ('qa', [(40.5, 55.4, PLUGIN, '')]), ('security', [(40.5, 51.6, PLUGIN, '')]), ('завршна порука', [(55.4, 58.6, PLUGIN, '')])]
fig, ax = nova(16, 9)
ax.grid(axis='y', visible=False); ax.grid(axis='x', color=MREZA, linewidth=0.8)
for i, (ime, delovi) in enumerate(TOK):
    for od, do, boja, opis in delovi:
        ax.barh(i, do - od, left=od, height=0.55, color=boja, edgecolor=POVRSINA, linewidth=1.5)
        if opis:
            ax.text(do + 0.6, i, opis, va='center', fontsize=10.5, color=TEKST2)
ax.set_yticks(range(len(TOK)), [t[0] for t in TOK]); ax.invert_yaxis()
ax.set_xlabel('минути од захтева')
ax.axvline(17.9, color=PRAZAN, linewidth=1, linestyle='--')
naslov(fig, 'Рунда 7, пет независних задатака: паралелни рад је спорији')
sacuvaj(fig, '05-runda7-tok.png', 'Радници у два таласа (3 + 2); сваки је покретао и цео пакет тестова у свом worktree-у.')

# 6. paket testova
fig, ax = nova(12, 7)
TESTOVI = [('цео пакет\n(589 тестова)', 388), ('без прегледача, --brzo\n(506 тестова)', 37), ('само прегледач\n(83 теста)', 336)]
ax.bar(range(3), [t[1] for t in TESTOVI], 0.55, color=PLUGIN, edgecolor=POVRSINA, linewidth=1.5)
for i, t in enumerate(TESTOVI):
    ax.text(i, t[1] + 8, '%d s' % t[1], ha='center', va='bottom', fontsize=13,
            bbox=dict(facecolor=POVRSINA, edgecolor='none', pad=1.5))   # mreza ne prolazi kroz oznaku
ax.set_xticks(range(3), [t[0] for t in TESTOVI])
ax.set_ylabel('трајање (s)')
naslov(fig, 'Тестови кроз прегледач су 87 % трајања пакета')
ax.set_ylim(0, 450)
sacuvaj(fig, '06-trajanje-testova.png', 'Мерено на копији пројекта плагина, 2026-11-12.')
print('folder:', IZLAZ)
