"""Consulta a biblioteca de cartas do formato (cartas/cartas.db).

Exemplos:
    python cartas.py buscar "contadores de dano banco"      busca no texto (português ou inglês)
    python cartas.py buscar Dragapult
    python cartas.py mostrar TWM-130                         ficha completa (ID, nome em inglês ou português)
    python cartas.py mostrar "Pesquisa de Professores"
    python cartas.py listar --categoria Treinador --subtipo Apoiador
    python cartas.py listar --categoria Pokémon --tipo Fogo --ex
    python cartas.py resumo                                  quantas cartas por pasta
    python cartas.py atualizar                               refaz cartas/ a partir da base do simulador
"""
import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'cartas' / 'cartas.db'


def con():
    if not DB.exists():
        print('Biblioteca ainda não gerada; criando…')
        subprocess.run([sys.executable, str(ROOT / 'tools' / 'export_cartas.py')], check=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def find(c, q):
    r = c.execute('SELECT * FROM cartas WHERE id = ? COLLATE NOCASE', (q,)).fetchone()
    if r:
        return [r]
    r = c.execute('SELECT c.* FROM impressoes i JOIN cartas c ON c.id = i.carta_id WHERE i.codigo = ? COLLATE NOCASE',
                  (q.replace(' ', '-'),)).fetchone()
    if r:
        return [r]
    rows = c.execute('SELECT * FROM cartas WHERE nome = ? COLLATE NOCASE OR nome_pt = ? COLLATE NOCASE', (q, q)).fetchall()
    if rows:
        return rows
    return c.execute('SELECT * FROM cartas WHERE nome LIKE ? OR nome_pt LIKE ? ORDER BY nome LIMIT 30',
                     (f'%{q}%', f'%{q}%')).fetchall()


def ficha(r):
    d = json.loads(r['json'])
    print(f"\n{d['nome']}  ({d['nome_pt']})  [{d['id']}]  — {r['pasta']}")
    if d['categoria'] == 'Pokémon':
        print(f"  {d['estagio']}{' de ' + d['evolui_de'] if d['evolui_de'] else ''} · {'/'.join(d['tipo'])} · "
              f"{d['hp']} PS · fraqueza {d['fraqueza'] or '—'} · resistência {d['resistencia'] or '—'} · "
              f"recuo {d['recuo']}")
        for h in d['habilidades']:
            print(f"  Habilidade: {h['nome_pt'] or h['nome']} ({h['nome']})")
            print(f"     {h['texto_pt'] or h['texto']}")
        for a in d['ataques']:
            print(f"  [{' '.join(a['custo']) or '—'}] {a['nome_pt'] or a['nome']} ({a['nome']}) {a['dano']}")
            t = a['texto_pt'] or a['texto']
            if t:
                print(f'     {t}')
    else:
        print(f"  {d['categoria']} · {d['subtipo']}{' · ACE SPEC' if d.get('ace_spec') else ''}")
        print(f"  {d.get('texto_pt') or d.get('texto')}")
        if d.get('texto_pt') and d.get('texto'):
            print(f"  (EN) {d['texto']}")
    for x in d['regras']:
        print(f'  • {x}')
    print('  Impressões: ' + ', '.join(i['codigo'] for i in d['impressoes']))
    st = d['simulador']
    print(f"  Simulador: {st['status']}" + ''.join(f'\n     - {p}' for p in st['pendencias']))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('buscar')
    b.add_argument('texto', nargs='+')
    b.add_argument('--limite', type=int, default=40)
    m = sub.add_parser('mostrar')
    m.add_argument('carta', nargs='+')
    lst = sub.add_parser('listar')
    lst.add_argument('--categoria', choices=['Pokémon', 'Treinador', 'Energia'])
    lst.add_argument('--subtipo', help='Apoiador, Item, Ferramenta, Estádio, Básico, Estágio 1, Energia Especial…')
    lst.add_argument('--tipo', help='Planta, Fogo, Água, Elétrico, Psíquico, Lutador, Escuridão, Metal, Dragão, Incolor')
    lst.add_argument('--ex', action='store_true', help='só Pokémon ex')
    lst.add_argument('--pendentes', action='store_true', help='só cartas ainda não 100%% implementadas no simulador')
    sub.add_parser('resumo')
    sub.add_parser('atualizar')
    a = ap.parse_args()

    if a.cmd == 'atualizar':
        subprocess.run([sys.executable, str(ROOT / 'tools' / 'export_cartas.py')], check=True)
        return
    c = con()
    if a.cmd == 'buscar':
        q = ' '.join(a.texto)
        rows = []
        try:
            terms = ' '.join(f'"{t}"*' for t in q.split())
            rows = c.execute('SELECT c.* FROM busca b JOIN cartas c ON c.id = b.id WHERE busca MATCH ? '
                             'ORDER BY rank LIMIT ?', (terms, a.limite)).fetchall()
        except sqlite3.OperationalError:
            pass
        if not rows:
            like = f'%{q}%'
            rows = c.execute('SELECT * FROM cartas WHERE nome LIKE ? OR nome_pt LIKE ? OR texto LIKE ? OR '
                             'texto_pt LIKE ? LIMIT ?', (like, like, like, like, a.limite)).fetchall()
        for r in rows:
            print(f"{r['id']:<11} {r['nome']:<32} {r['nome_pt'] or '':<32} {r['pasta']}")
        print(f'{len(rows)} resultado(s)')
    elif a.cmd == 'mostrar':
        rows = find(c, ' '.join(a.carta))
        if not rows:
            print('Carta não encontrada.')
        if len(rows) > 3:
            for r in rows:
                print(f"{r['id']:<11} {r['nome']:<32} {r['nome_pt']}")
            return
        for r in rows:
            ficha(r)
    elif a.cmd == 'listar':
        w, args = [], []
        if a.categoria:
            w.append('categoria = ?')
            args.append(a.categoria)
        if a.subtipo:
            w.append('subtipo = ? COLLATE NOCASE')
            args.append(a.subtipo)
        if a.tipo:
            w.append("(tipo = ? COLLATE NOCASE OR tipo LIKE ?)")
            args += [a.tipo, f'%{a.tipo}%']
        if a.ex:
            w.append('pokemon_ex = 1')
        if a.pendentes:
            w.append("status_simulador != 'implementada'")
        rows = c.execute('SELECT * FROM cartas' + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY nome',
                         args).fetchall()
        for r in rows:
            print(f"{r['id']:<11} {r['nome']:<32} {r['nome_pt'] or '':<32} {r['subtipo'] or '':<16} {r['tipo'] or ''}")
        print(f'{len(rows)} carta(s)')
    elif a.cmd == 'resumo':
        for r in c.execute('SELECT pasta, COUNT(*) n FROM cartas GROUP BY pasta ORDER BY pasta'):
            print(f"{r['pasta']:<40} {r['n']}")
        n = c.execute('SELECT COUNT(*) FROM cartas').fetchone()[0]
        st = dict(c.execute('SELECT status_simulador, COUNT(*) FROM cartas GROUP BY 1').fetchall())
        print(f'\nTotal: {n} cartas · simulador: {st}')


if __name__ == '__main__':
    main()
