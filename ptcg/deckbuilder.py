"""Lógica do montador de decks da interface (web/decks.html): busca de cartas, ver/salvar/duplicar decks.

As categorias seguem as pastas de `cartas/` (ver tools/export_cartas.py):
    Treinadores/{Apoiadores,Itens,Ferramentas,Estadios}   Pokemon/<Tipo>   Pokemon_EX/<Tipo>   Energias/<Tipo|Especiais>
Só decks em decks/meus/ podem ser criados ou sobrescritos; qualquer deck pode ser lido ou duplicado.
"""
import re
from collections import Counter
from datetime import date

from .carddb import db, norm
from .decks import DECK_DIR, deck_to_text, list_decks, load_deck, support_report, validate

MIN_BUSCA = 3
MAX_RESULTADOS = 300
TIPO = {'G': 'Planta', 'R': 'Fogo', 'W': 'Água', 'L': 'Elétrico', 'P': 'Psíquico', 'F': 'Lutador',
        'D': 'Escuridão', 'M': 'Metal', 'N': 'Dragão', 'C': 'Incolor', 'Y': 'Fada'}
SUB_TREINADOR = {'supporter': 'Apoiadores', 'item': 'Itens', 'tool': 'Ferramentas', 'stadium': 'Estadios'}
ROTULO_SUB = {'Apoiadores': 'Apoiadores', 'Itens': 'Itens', 'Ferramentas': 'Ferramentas', 'Estadios': 'Estádios',
              'Especiais': 'Especiais'}
GRUPOS = [('Pokemon', 'Pokémon'), ('Pokemon_EX', 'Pokémon ex'), ('Treinadores', 'Treinadores'),
          ('Energias', 'Energias')]


def categoria(d) -> tuple:
    """(grupo, sub) = pasta da carta em cartas/, ex.: ('Pokemon_EX', 'Fogo')."""
    if d.kind == 'trainer':
        return 'Treinadores', SUB_TREINADOR.get(d.subtype, 'Outros')
    if d.kind == 'energy':
        return 'Energias', ('Especiais' if not d.basic_energy else TIPO.get(d.provides, 'Incolor'))
    t = d.types[0] if d.types else 'C'
    return ('Pokemon_EX' if d.is_ex else 'Pokemon'), TIPO.get(t, 'Incolor')


def lista_categorias() -> list:
    """Opções dos filtros: [{grupo, rotulo, subs: [{sub, rotulo, n}]}] (só o que existe na base)."""
    cont = Counter(categoria(d) for d in db().cards.values())
    out = []
    for g, rot in GRUPOS:
        subs = sorted(((s, n) for (gg, s), n in cont.items() if gg == g), key=lambda x: x[0])
        out.append({'grupo': g, 'rotulo': rot, 'n': sum(n for _, n in subs),
                    'subs': [{'sub': s, 'rotulo': ROTULO_SUB.get(s, s), 'n': n} for s, n in subs]})
    return out


def _resumo(d) -> str:
    if d.kind == 'pokemon':
        partes = [f'{a.name}' for a in d.abilities] + [f'{a.name} {a.damage or ""}{a.suffix}'.strip() for a in d.attacks]
        return ' · '.join(partes)
    return (d.text or '').replace('\n', ' ')[:140]


def resumo_carta(d) -> dict:
    g, s = categoria(d)
    return {'id': d.id, 'name': d.name, 'name_pt': d.name_pt if d.name_pt and d.name_pt != d.name else '',
            'kind': d.kind, 'grupo': g, 'sub': s, 'types': list(d.types), 'stage': d.stage, 'hp': d.hp,
            'evolves_from': d.evolves_from, 'ex': bool(d.kind == 'pokemon' and d.is_ex),
            'ace': bool(d.ace_spec), 'basic_energy': bool(d.kind == 'energy' and d.basic_energy),
            'basic': bool(d.is_basic), 'provides': d.provides if d.kind == 'energy' else None,
            'print': (d.prints[0] if d.prints else d.id).replace('-', ' ', 1), 'status': d.status,
            'resumo': _resumo(d)}


def buscar(q: str = '', grupo: str = '', sub: str = '', limite: int = MAX_RESULTADOS) -> dict:
    """Filtra por categoria e/ou nome (en/pt, ≥3 letras). Sem nenhum dos dois devolve vazio."""
    q = norm(q or '')
    if len(q) < MIN_BUSCA and not grupo:
        return {'cards': [], 'total': 0, 'dica': f'Digite ao menos {MIN_BUSCA} letras ou escolha uma categoria.'}
    achadas = []
    for d in db().cards.values():
        g, s = categoria(d)
        if grupo and g != grupo or sub and s != sub:
            continue
        if len(q) >= MIN_BUSCA:
            nomes = [norm(d.name)] + ([norm(d.name_pt)] if d.name_pt else [])
            if not any(q in n for n in nomes):
                continue
        achadas.append(d)
    achadas.sort(key=lambda d: (norm(d.name) != q, not norm(d.name).startswith(q), norm(d.name), d.id))
    return {'cards': [resumo_carta(d) for d in achadas[:limite]], 'total': len(achadas)}


# ------------------------------------------------------------------ decks
def nome_seguro(s: str) -> str:
    return re.sub(r'[^\w\-]+', '_', (s or '').strip(), flags=re.UNICODE).strip('_')


def _caminho_meus(nome: str):
    n = nome_seguro(nome.split('/')[-1])
    if not n:
        raise ValueError('Nome de deck inválido.')
    return DECK_DIR / 'meus' / f'{n}.txt', f'meus/{n}'


def ver_deck(nome: str) -> dict:
    d = load_deck(nome, strict=False)
    D = db()
    cont = Counter(d.cards)
    cartas = []
    for cid, n in cont.items():
        r = resumo_carta(D.get(cid))
        r['n'] = n
        cartas.append(r)
    cartas.sort(key=lambda c: ({'pokemon': 0, 'trainer': 1, 'energy': 2}[c['kind']], -c['n'], c['name']))
    meta = {k: v for k, v in d.meta.items() if k not in ('errors', 'path')}
    return {'name': nome, 'editavel': nome.startswith('meus/'),
            'cards': cartas, 'total': len(d.cards), 'meta': meta, 'errors': d.meta['errors'],
            'pending': [f'{x.name}: {s}' for x, _, s in support_report(d.cards)]}


def avaliar(itens: list) -> dict:
    """Valida uma lista [{id, n}] sem salvar."""
    cards = _expandir(itens)
    return {'total': len(cards), 'errors': validate(cards),
            'pending': [f'{x.name}: {s}' for x, _, s in support_report(cards)]}


def _expandir(itens: list) -> list:
    D = db()
    cards = []
    for it in itens:
        if it['id'] not in D.cards:
            raise ValueError(f'Carta desconhecida: {it["id"]}')
        cards += [it['id']] * max(0, int(it['n']))
    return cards


def salvar(nome: str, itens: list, sobrescrever: bool, meta: dict | None = None) -> dict:
    """Grava em decks/meus/. Rascunhos incompletos (≠60 cartas) são aceitos; os avisos voltam na resposta."""
    path, rel = _caminho_meus(nome)
    existe = path.exists()
    if existe and not sobrescrever:
        raise FileExistsError(f'Já existe {rel}. Use "Salvar" no deck aberto ou escolha outro nome.')
    cards = _expandir(itens)
    if not cards:
        raise ValueError('O deck está vazio.')
    meta = {k: v for k, v in (meta or {}).items() if k not in ('errors', 'path', 'atualizado') and isinstance(v, (str, int, float))}
    meta.setdefault('formato', 'TEF-30C (H/I/J)')
    meta['atualizado'] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(deck_to_text(cards, meta), encoding='utf-8')
    try:
        from .logbook import registrar
        registrar('decks', f'{"atualizou" if existe else "criou"} {rel}.txt pelo montador', cartas=len(cards))
    except Exception:
        pass
    return {'ok': True, 'name': rel, 'criado': not existe, **avaliar(itens)}


def duplicar(origem: str, destino: str | None = None) -> dict:
    """Copia qualquer deck para decks/meus/<destino> (padrão: nome do original, com sufixo se já existir)."""
    d = load_deck(origem, strict=False)
    base = nome_seguro(destino or origem.split('/')[-1])
    if not base:
        raise ValueError('Nome de deck inválido.')
    n, i = base, 2
    if not destino:
        while (DECK_DIR / 'meus' / f'{n}.txt').exists():
            n, i = f'{base}_{i}', i + 1
    elif (DECK_DIR / 'meus' / f'{n}.txt').exists():
        raise FileExistsError(f'Já existe meus/{n}.')
    meta = {k: v for k, v in d.meta.items() if k not in ('errors', 'path')}
    meta['copiado_de'] = origem
    itens = [{'id': c, 'n': k} for c, k in Counter(d.cards).items()]
    return salvar(n, itens, False, meta)


def decks_disponiveis() -> list:
    """Nome e rótulo de cada deck para os seletores (meus primeiro)."""
    out = []
    for n in list_decks():
        try:
            d = load_deck(n, strict=False)
            m = d.meta
            rot = (f'{m["place"]}º ' if m.get('place') else '') + (m.get('archetype') or n.split('/')[-1]) \
                + (f' — {m["player"]}' if m.get('player') else '')
            out.append({'name': n, 'label': rot, 'ok': not m['errors'], 'meu': n.startswith('meus/')})
        except Exception as e:
            out.append({'name': n, 'label': n, 'ok': False, 'meu': n.startswith('meus/'), 'erro': str(e)})
    out.sort(key=lambda x: (not x['meu'], x['name']))
    return out
