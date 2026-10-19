"""Lógica da página de exploração de cartas (web/cartas.html): filtros, detalhe de cada carta e imagens.

Reaproveita as categorias do montador (pastas de cartas/). As imagens vêm de imagens/cartas/ (baixar_imagens.py).
"""
import json
from collections import Counter
from pathlib import Path

from .carddb import db, norm
from .deckbuilder import MIN_BUSCA, TIPO, categoria, resumo_carta

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / 'imagens' / 'cartas'
PAGINA = 60
ESTAGIOS = {0: 'Básico', 1: 'Estágio 1', 2: 'Estágio 2'}
STATUS_ROT = {'ok': 'implementada', 'partial': 'parcial', 'missing': 'pendente'}

_RAW = None


def _raw():
    global _RAW
    if _RAW is None:
        base = Path(__file__).resolve().parent / 'data'
        cards = json.load(open(base / 'cards.json', encoding='utf-8'))
        pt = json.load(open(base / 'cards_pt.json', encoding='utf-8')) if (base / 'cards_pt.json').exists() else {}
        _RAW = (cards, pt)
    return _RAW


def pendencias(d) -> list:
    """O que ainda não está implementado na carta: [{onde, nome, status, nota}]."""
    out = []
    for a in d.attacks:
        if a.impl is not None and a.impl.status != 'ok':
            out.append({'onde': 'Ataque', 'nome': a.name, 'status': a.impl.status, 'nota': a.impl.note})
    for a in d.abilities:
        if a.impl is None or a.impl.status != 'ok':
            out.append({'onde': 'Habilidade', 'nome': a.name, 'status': a.impl.status if a.impl else 'missing',
                        'nota': a.impl.note if a.impl else 'não implementada'})
    if d.kind != 'pokemon' and d.impl is not None and d.impl.status != 'ok':
        out.append({'onde': 'Efeito', 'nome': d.name, 'status': d.impl.status, 'nota': d.impl.note or 'efeito parcial'})
    return out


def tem_imagem(cid: str):
    return {q: _arquivo(q, cid) is not None for q in ('baixa', 'alta')}


def _arquivo(qual: str, cid: str):
    for ext in ('webp', 'png', 'jpg'):
        p = IMG_DIR / qual / f'{cid}.{ext}'
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def arquivo_imagem(qual: str, cid: str):
    """Caminho da imagem (alta cai para baixa e vice-versa) ou None. `cid` é validado contra a base."""
    if cid not in db().cards:
        return None
    outro = 'baixa' if qual == 'alta' else 'alta'
    return _arquivo(qual if qual in ('baixa', 'alta') else 'baixa', cid) or _arquivo(outro, cid)


def opcoes() -> dict:
    D = db()
    sets = _raw()[0]['sets']
    cont = Counter(d.status for d in D.cards.values())
    colecoes = Counter(p.rsplit('-', 1)[0] for d in D.cards.values() for p in (d.prints or [d.id]))
    return {'status': {STATUS_ROT[k]: cont.get(k, 0) for k in STATUS_ROT}, 'total': len(D.cards),
            'colecoes': [{'code': c, 'nome': sets.get(c, {}).get('name', c), 'n': n}
                         for c, n in sorted(colecoes.items(), key=lambda x: sets.get(x[0], {}).get('date', ''))],
            'com_imagem': sum(1 for cid in D.cards if _arquivo('baixa', cid) or _arquivo('alta', cid)),
            'estagios': ESTAGIOS, 'tipos': TIPO, 'min_busca': MIN_BUSCA}


def filtrar(q='', grupo='', sub='', status='', tipo='', estagio='', colecao='', no_texto=False, offset=0) -> dict:
    """status: '' | ok | partial | missing | problema (parcial + pendente). Devolve uma página de PAGINA cartas."""
    D = db()
    q = norm(q or '')
    if 0 < len(q) < MIN_BUSCA:
        return {'cards': [], 'total': 0, 'dica': f'Digite ao menos {MIN_BUSCA} letras no nome.'}
    achadas = []
    for d in D.cards.values():
        g, s = categoria(d)
        if grupo and g != grupo or sub and s != sub:
            continue
        if status == 'problema':
            if d.status == 'ok':
                continue
        elif status and d.status != status:
            continue
        if tipo and tipo not in (d.types if d.kind == 'pokemon' else [d.provides] if d.provides else []):
            continue
        if estagio != '' and (d.kind != 'pokemon' or d.stage != int(estagio)):
            continue
        if colecao and not any(p.rsplit('-', 1)[0] == colecao for p in (d.prints or [d.id])):
            continue
        if q:
            alvo = [norm(d.name)] + ([norm(d.name_pt)] if d.name_pt else [])
            if no_texto:
                alvo += [norm(d.text or '')] + [norm(x.text or '') for x in d.attacks + d.abilities] \
                    + [norm(x.name) for x in d.attacks + d.abilities]
            if not any(q in t for t in alvo):
                continue
        achadas.append(d)
    achadas.sort(key=lambda d: (bool(q) and not norm(d.name).startswith(q), norm(d.name), d.id))
    pag = achadas[offset:offset + PAGINA]
    out = []
    for d in pag:
        r = resumo_carta(d)
        r['imagem'] = _arquivo('baixa', d.id) is not None or _arquivo('alta', d.id) is not None
        if d.status != 'ok':
            r['pendencias'] = [f'{p["onde"]} {p["nome"]}: {p["nota"]}' for p in pendencias(d)]
        out.append(r)
    return {'cards': out, 'total': len(achadas), 'offset': offset, 'pagina': PAGINA}


def detalhe(cid: str) -> dict:
    D = db()
    d = D.get(cid)
    raw, pt = _raw()
    p = pt.get(cid, {})
    sets = raw['sets']
    r = resumo_carta(d)
    r.update({
        'regulamento': raw['cards'].get(cid, {}).get('regulation'), 'status_rot': STATUS_ROT[d.status],
        'estagio_rot': ESTAGIOS.get(d.stage) if d.kind == 'pokemon' else None,
        'categoria_rot': {'pokemon': 'Pokémon', 'trainer': 'Treinador', 'energy': 'Energia'}[d.kind],
        'fraqueza': f'{TIPO[d.weakness]} ×2' if d.weakness else None,
        'resistencia': f'{TIPO[d.resistance]} -{d.resistance_value}' if d.resistance else None,
        'recuo': d.retreat, 'tags': sorted(d.tags), 'premios': d.base_prizes if d.kind == 'pokemon' else None,
        'texto': d.text, 'texto_pt': p.get('text') or '', 'subtipo': d.subtype,
        'pendencias': pendencias(d), 'imagem': tem_imagem(cid),
        'tipos_rot': [TIPO[t] for t in d.types], 'fornece_rot': TIPO.get(d.provides) if d.provides else None,
    })
    pab, pat = p.get('abilities') or [], p.get('attacks') or []
    r['habilidades'] = [{'nome': a.name, 'nome_pt': (pab[i].get('name') if i < len(pab) else '') or '', 'texto': a.text,
                         'texto_pt': (pab[i].get('text') if i < len(pab) else '') or '',
                         'status': a.impl.status if a.impl else 'missing', 'nota': a.impl.note if a.impl else 'não implementada'}
                        for i, a in enumerate(d.abilities)]
    r['ataques'] = [{'nome': a.name, 'nome_pt': (pat[i].get('name') if i < len(pat) else '') or '',
                     'custo': list(a.cost), 'dano': f'{a.damage or ""}{a.suffix}' or '', 'texto': a.text,
                     'texto_pt': (pat[i].get('text') if i < len(pat) else '') or '',
                     'status': a.impl.status if a.impl else 'ok', 'nota': a.impl.note if a.impl else ''}
                    for i, a in enumerate(d.attacks)]
    r['impressoes'] = [{'codigo': x.replace('-', ' ', 1), 'colecao': sets.get(x.rsplit('-', 1)[0], {}).get('name', ''),
                        'data': sets.get(x.rsplit('-', 1)[0], {}).get('date', '')} for x in (d.prints or [d.id])]
    mesma = [x for x in D.named(d.name) if x.id != cid]
    r['outras_versoes'] = [{'id': x.id, 'print': (x.prints[0] if x.prints else x.id).replace('-', ' ', 1)} for x in mesma]
    if d.kind == 'pokemon':
        r['evolui_para'] = sorted({x.name for x in D.cards.values() if x.evolves_from == d.name})
    return r
