"""Gera a biblioteca de cartas do formato (coleções TEF a 30C, marcas H/I/J) na pasta cartas/.

    python tools/export_cartas.py            (refaz tudo a partir de ptcg/data/*.json)

Estrutura gerada:
    cartas/cartas.db              banco SQLite (todas as cartas, ataques, Habilidades, impressões, busca por texto)
    cartas/Treinadores.json       os 3 arquivos consolidados
    cartas/Pokemon.json
    cartas/Energias.json
    cartas/Treinadores/{Apoiadores,Itens,Ferramentas,Estadios}/<Nome>__<ID>.json
    cartas/Pokemon/Pokemon_EX/<Tipo>/…   e   cartas/Pokemon/<Tipo>/…
    cartas/Energias/<Tipo>/…     e   cartas/Energias/Especiais/…
    _indice.md em cada pasta (lista legível: nome, nome em português, o que a carta faz)
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ptcg.carddb import db  # noqa: E402

OUT = ROOT / 'cartas'
TIPO = {'G': 'Planta', 'R': 'Fogo', 'W': 'Água', 'L': 'Elétrico', 'P': 'Psíquico', 'F': 'Lutador',
        'D': 'Escuridão', 'M': 'Metal', 'N': 'Dragão', 'C': 'Incolor', 'Y': 'Fada'}
PASTA_TIPO = {'G': 'Planta', 'R': 'Fogo', 'W': 'Agua', 'L': 'Eletrico', 'P': 'Psiquico', 'F': 'Lutador',
              'D': 'Escuridao', 'M': 'Metal', 'N': 'Dragao', 'C': 'Incolor', 'Y': 'Fada'}
SUBTIPO_TREINADOR = {'supporter': ('Apoiador', 'Apoiadores'), 'item': ('Item', 'Itens'),
                     'tool': ('Ferramenta', 'Ferramentas'), 'stadium': ('Estádio', 'Estadios')}
ESTAGIO = {0: 'Básico', 1: 'Estágio 1', 2: 'Estágio 2'}
STATUS = {'ok': 'implementada', 'partial': 'parcial', 'missing': 'pendente'}
FORMATO = ('TEF', '30C')


def slug(s):
    s = re.sub(r"[’'`]", '', s)
    s = re.sub(r'[^\w\-]+', '_', s, flags=re.UNICODE).strip('_')
    return s or 'carta'


def regras(d):
    out = []
    if d.kind == 'pokemon':
        if 'mega' in d.tags:
            out.append('Pokémon Mega Evolução ex: quando for Nocauteado, o oponente pega 3 cartas de Prêmio.')
        elif 'ex' in d.tags:
            out.append('Pokémon ex: quando for Nocauteado, o oponente pega 2 cartas de Prêmio.')
        if 'tera' in d.tags:
            out.append('Tera: enquanto estiver no Banco, não recebe dano de ataques.')
        for t, txt in (('ancient', 'Antigo'), ('future', 'Futuro')):
            if t in d.tags:
                out.append(f'Pokémon {txt}.')
    if d.ace_spec:
        out.append('ACE SPEC: só pode haver 1 carta ACE SPEC no baralho.')
    if d.kind == 'trainer' and d.subtype == 'supporter':
        out.append('Apoiador: só pode jogar 1 carta de Apoiador por turno.')
    if d.kind == 'trainer' and d.subtype == 'stadium':
        out.append('Estádio: só pode jogar 1 carta de Estádio por turno; fica em jogo até ser substituído.')
    if d.kind == 'trainer' and d.subtype == 'tool':
        out.append('Ferramenta: ligue a um dos seus Pokémon (1 por Pokémon); fica ligada.')
    return out


def card_record(d, pt, raw, sets):
    p = pt.get(d.id, {})
    rec = {
        'id': d.id, 'nome': d.name, 'nome_pt': p.get('name') or d.name_pt or d.name,
        'categoria': {'pokemon': 'Pokémon', 'trainer': 'Treinador', 'energy': 'Energia'}[d.kind],
    }
    if d.kind == 'pokemon':
        rec.update({
            'tipo': [TIPO[t] for t in d.types], 'hp': d.hp, 'estagio': ESTAGIO.get(d.stage, d.stage),
            'evolui_de': d.evolves_from, 'pokemon_ex': d.is_ex, 'mega': d.is_mega, 'tera': 'tera' in d.tags,
            'fraqueza': f'{TIPO[d.weakness]} ×2' if d.weakness else None,
            'resistencia': f'{TIPO[d.resistance]} -{d.resistance_value}' if d.resistance else None,
            'recuo': d.retreat, 'premios_ao_ser_nocauteado': d.base_prizes,
            'habilidades': [], 'ataques': [],
        })
        pab = p.get('abilities') or []
        for i, a in enumerate(d.abilities):
            x = pab[i] if i < len(pab) else {}
            rec['habilidades'].append({'nome': a.name, 'nome_pt': x.get('name'), 'texto': a.text,
                                       'texto_pt': x.get('text'),
                                       'simulador': STATUS.get(a.impl.status if a.impl else 'missing')})
        pat = p.get('attacks') or []
        for i, a in enumerate(d.attacks):
            x = pat[i] if i < len(pat) else {}
            rec['ataques'].append({'nome': a.name, 'nome_pt': x.get('name'),
                                   'custo': [TIPO[c] for c in a.cost], 'dano': f'{a.damage or ""}{a.suffix}' or '—',
                                   'texto': a.text, 'texto_pt': x.get('text') or ('' if not a.text else None),
                                   'simulador': STATUS.get(a.impl.status if a.impl else 'ok')})
    elif d.kind == 'trainer':
        rec.update({'subtipo': SUBTIPO_TREINADOR.get(d.subtype, (d.subtype,))[0], 'ace_spec': d.ace_spec,
                    'texto': d.text, 'texto_pt': p.get('text')})
        if d.as_pokemon:
            rec['fossil'] = {'hp': d.hp}
    else:
        basic = d.basic_energy
        rec.update({'subtipo': 'Energia Básica' if basic else 'Energia Especial', 'ace_spec': d.ace_spec,
                    'fornece': TIPO.get(d.provides) if basic else None,
                    'texto': d.text if not basic else f'Fornece 1 Energia de {TIPO[d.provides]}.',
                    'texto_pt': p.get('text') if not basic else f'Fornece 1 Energia de {TIPO[d.provides]}.'})
    rec['regras'] = regras(d)
    rec['regulamento'] = raw.get('regulation')
    rec['impressoes'] = [{'codigo': x, 'colecao': sets.get(x.rsplit('-', 1)[0], {}).get('name'),
                          'data': sets.get(x.rsplit('-', 1)[0], {}).get('date')} for x in d.prints]
    rec['simulador'] = {'status': STATUS[d.status], 'pendencias': _pending(d)}
    return rec


def _pending(d):
    out = []
    for a in d.attacks:
        if a.impl is not None and a.impl.status != 'ok':
            out.append(f'Ataque {a.name}: {a.impl.note}')
    for a in d.abilities:
        if a.impl is None or a.impl.status != 'ok':
            out.append(f'Habilidade {a.name}: {a.impl.note if a.impl else "não implementada"}')
    if d.kind != 'pokemon' and d.impl is not None and d.impl.status != 'ok':
        out.append(d.impl.note or 'efeito parcial')
    return out


def resumo(rec):
    """Uma linha dizendo o que a carta faz (português quando disponível)."""
    if rec['categoria'] == 'Pokémon':
        parts = []
        for h in rec['habilidades']:
            parts.append(f"Habilidade {h['nome_pt'] or h['nome']}: {h['texto_pt'] or h['texto']}")
        for a in rec['ataques']:
            t = a['texto_pt'] if a['texto_pt'] is not None else a['texto']
            parts.append(f"{a['nome_pt'] or a['nome']} [{''.join(c[0] for c in a['custo'])}] {a['dano']}"
                         + (f": {t}" if t else ''))
        return ' | '.join(parts)
    return rec.get('texto_pt') or rec.get('texto') or ''


def destino(rec):
    if rec['categoria'] == 'Treinador':
        sub = {'Apoiador': 'Apoiadores', 'Item': 'Itens', 'Ferramenta': 'Ferramentas', 'Estádio': 'Estadios'}
        return Path('Treinadores') / sub.get(rec['subtipo'], 'Outros')
    if rec['categoria'] == 'Energia':
        if rec['subtipo'] == 'Energia Especial':
            return Path('Energias') / 'Especiais'
        code = next(k for k, v in TIPO.items() if v == rec['fornece'])
        return Path('Energias') / PASTA_TIPO[code]
    code = next(k for k, v in TIPO.items() if v == rec['tipo'][0])
    if rec['pokemon_ex']:
        return Path('Pokemon') / 'Pokemon_EX' / PASTA_TIPO[code]
    return Path('Pokemon') / PASTA_TIPO[code]


SCHEMA = """
CREATE TABLE cartas (
  id TEXT PRIMARY KEY, nome TEXT, nome_pt TEXT, categoria TEXT, subtipo TEXT, tipo TEXT, hp INTEGER,
  estagio TEXT, evolui_de TEXT, pokemon_ex INTEGER, mega INTEGER, tera INTEGER, ace_spec INTEGER,
  fraqueza TEXT, resistencia TEXT, recuo INTEGER, premios INTEGER, regulamento TEXT,
  texto TEXT, texto_pt TEXT, resumo TEXT, pasta TEXT, arquivo TEXT, status_simulador TEXT, json TEXT);
CREATE TABLE ataques (carta_id TEXT, ordem INTEGER, nome TEXT, nome_pt TEXT, custo TEXT, dano TEXT,
  texto TEXT, texto_pt TEXT, status_simulador TEXT);
CREATE TABLE habilidades (carta_id TEXT, ordem INTEGER, nome TEXT, nome_pt TEXT, texto TEXT, texto_pt TEXT,
  status_simulador TEXT);
CREATE TABLE impressoes (codigo TEXT PRIMARY KEY, carta_id TEXT, colecao TEXT, data TEXT);
CREATE TABLE colecoes (codigo TEXT PRIMARY KEY, nome TEXT, data TEXT, no_formato INTEGER);
CREATE INDEX i_nome ON cartas(nome); CREATE INDEX i_nome_pt ON cartas(nome_pt);
CREATE INDEX i_cat ON cartas(categoria, subtipo, tipo); CREATE INDEX i_atk ON ataques(carta_id);
CREATE INDEX i_hab ON habilidades(carta_id); CREATE INDEX i_imp ON impressoes(carta_id);
CREATE VIEW v_pokemon AS SELECT * FROM cartas WHERE categoria='Pokémon';
CREATE VIEW v_treinadores AS SELECT * FROM cartas WHERE categoria='Treinador';
CREATE VIEW v_energias AS SELECT * FROM cartas WHERE categoria='Energia';
"""


def write_db(path, recs, sets):
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    fts = True
    try:
        con.execute("CREATE VIRTUAL TABLE busca USING fts5(id UNINDEXED, nome, nome_pt, texto, texto_pt, "
                    "tokenize='unicode61 remove_diacritics 2')")
    except sqlite3.OperationalError:
        fts = False
    lo, hi = sets[FORMATO[0]]['date'], sets[FORMATO[1]]['date']
    for code, s in sets.items():
        con.execute('INSERT INTO colecoes VALUES (?,?,?,?)', (code, s['name'], s['date'],
                                                             int(lo <= s['date'] <= hi)))
    for r, folder, fname in recs:
        texto = r.get('texto') or ''
        texto_pt = r.get('texto_pt') or ''
        if r['categoria'] == 'Pokémon':
            texto = ' '.join(f"{x['nome']}: {x['texto']}" for x in r['habilidades'] + r['ataques'])
            texto_pt = ' '.join(f"{x['nome_pt'] or x['nome']}: {x['texto_pt'] or ''}"
                                for x in r['habilidades'] + r['ataques'])
        con.execute('INSERT INTO cartas VALUES (' + ','.join('?' * 25) + ')', (
            r['id'], r['nome'], r['nome_pt'], r['categoria'], r.get('subtipo') or r.get('estagio'),
            '/'.join(r['tipo']) if r.get('tipo') else r.get('fornece'), r.get('hp'), r.get('estagio'),
            r.get('evolui_de'), int(bool(r.get('pokemon_ex'))), int(bool(r.get('mega'))), int(bool(r.get('tera'))),
            int(bool(r.get('ace_spec'))), r.get('fraqueza'), r.get('resistencia'), r.get('recuo'),
            r.get('premios_ao_ser_nocauteado'), r['regulamento'], texto, texto_pt, resumo(r), str(folder),
            fname, r['simulador']['status'], json.dumps(r, ensure_ascii=False)))
        for i, a in enumerate(r.get('ataques', [])):
            con.execute('INSERT INTO ataques VALUES (?,?,?,?,?,?,?,?,?)', (
                r['id'], i, a['nome'], a['nome_pt'], ''.join(c[0] for c in a['custo']), a['dano'], a['texto'],
                a['texto_pt'], a['simulador']))
        for i, h in enumerate(r.get('habilidades', [])):
            con.execute('INSERT INTO habilidades VALUES (?,?,?,?,?,?,?)', (
                r['id'], i, h['nome'], h['nome_pt'], h['texto'], h['texto_pt'], h['simulador']))
        for imp in r['impressoes']:
            con.execute('INSERT OR IGNORE INTO impressoes VALUES (?,?,?,?)',
                        (imp['codigo'], r['id'], imp['colecao'], imp['data']))
        if fts:
            con.execute('INSERT INTO busca VALUES (?,?,?,?,?)', (r['id'], r['nome'], r['nome_pt'], texto, texto_pt))
    con.commit()
    con.close()


def indice_md(title, items):
    lines = [f'# {title}', '', f'{len(items)} carta(s).', '',
             '| Carta | Nome em português | ID | O que faz | Simulador |', '|---|---|---|---|---|']
    for r, _, fname in sorted(items, key=lambda x: (x[0]['nome'], x[0]['id'])):
        txt = resumo(r).replace('|', '/').replace('\n', ' ')
        lines.append(f"| [{r['nome']}]({fname}) | {r['nome_pt']} | {r['id']} | {txt} | {r['simulador']['status']} |")
    return '\n'.join(lines) + '\n'


def main():
    D = db()
    raw = json.load(open(ROOT / 'ptcg' / 'data' / 'cards.json', encoding='utf-8'))
    ptp = ROOT / 'ptcg' / 'data' / 'cards_pt.json'
    pt = json.load(open(ptp, encoding='utf-8')) if ptp.exists() else {}
    sets = raw['sets']
    if OUT.exists():
        for sub in ('Treinadores', 'Pokemon', 'Energias'):
            shutil.rmtree(OUT / sub, ignore_errors=True)
    OUT.mkdir(exist_ok=True)
    recs = []
    for d in sorted(D.cards.values(), key=lambda x: (x.kind, x.name, x.id)):
        if d.id == 'UNKNOWN':
            continue
        r = card_record(d, pt, raw['cards'].get(d.id, {}), sets)
        folder = destino(r)
        fname = f"{slug(r['nome'])}__{slug(r['id'])}.json"
        (OUT / folder).mkdir(parents=True, exist_ok=True)
        (OUT / folder / fname).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
        recs.append((r, folder, fname))

    by_folder = defaultdict(list)
    for x in recs:
        by_folder[x[1]].append(x)
    for folder, items in by_folder.items():
        (OUT / folder / '_indice.md').write_text(indice_md(' / '.join(folder.parts), items), encoding='utf-8')

    groups = {'Treinadores': 'Treinador', 'Pokemon': 'Pokémon', 'Energias': 'Energia'}
    for fname, cat in groups.items():
        items = [x for x in recs if x[0]['categoria'] == cat]
        tree = defaultdict(list)
        for r, folder, f in items:
            tree['/'.join(folder.parts[1:])].append({**r, 'arquivo': f'{folder.as_posix()}/{f}'})
        doc = {'formato': f'{FORMATO[0]}–{FORMATO[1]} (marcas de regulamento H, I e J)', 'categoria': cat,
               'total': len(items), 'pastas': {k: len(v) for k, v in sorted(tree.items())},
               'cartas': {k: v for k, v in sorted(tree.items())}}
        (OUT / f'{fname}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
        sub_folders = sorted({x[1] for x in items})
        md = [f'# {fname}', '', f'{len(items)} cartas.', '']
        md += [f'- [{"/".join(f.parts[1:])}]({"/".join(f.parts[1:])}/_indice.md): {len(by_folder[f])}'
               for f in sub_folders]
        (OUT / fname / '_indice.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    write_db(OUT / 'cartas.db', recs, sets)
    stats = defaultdict(int)
    for r, folder, _ in recs:
        stats[folder.as_posix()] += 1
    print(f'{len(recs)} cartas exportadas para {OUT}')
    for k in sorted(stats):
        print(f'  {k:<40} {stats[k]}')


if __name__ == '__main__':
    main()
