"""Serialização do estado do jogo para a interface (respeitando informação oculta)."""
from __future__ import annotations


def card_info(d):
    return {
        'id': d.id, 'name': d.name, 'name_pt': d.name_pt, 'kind': d.kind, 'subtype': d.subtype,
        'types': list(d.types), 'hp': d.hp, 'stage': d.stage, 'evolves_from': d.evolves_from, 'retreat': d.retreat,
        'weakness': d.weakness, 'resistance': d.resistance, 'resistance_value': d.resistance_value,
        'tags': sorted(d.tags), 'text': d.text, 'provides': d.provides, 'status': d.status,
        'prints': d.prints[:3],
        'attacks': [{'name': a.name, 'cost': a.cost, 'damage': a.damage, 'suffix': a.suffix, 'text': a.text,
                     'status': a.impl.status if a.impl else 'ok'} for a in d.attacks],
        'abilities': [{'name': a.name, 'text': a.text, 'status': a.impl.status if a.impl else 'missing'}
                      for a in d.abilities],
    }


def game_cards(g):
    ids = set(g.deck_lists[0]) | set(g.deck_lists[1])
    for p in g.players:
        for z in p.zones().values():
            ids |= {c.d.id for c in z}
        for s in p.in_play():
            ids |= {c.d.id for c in s.all_cards()}
    if g.stadium is not None:
        ids.add(g.stadium.d.id)
    return {i: card_info(g.db.get(i)) for i in ids if i in g.db.cards}


def _slot(g, s):
    if s is None:
        return None
    energy = []
    for e, units in g.energy_units(s):
        energy.append({'id': e.d.id, 'name': e.name,
                       'types': ['*' if len(u) > 1 else next(iter(u)) for u in units]})
    return {
        'sid': s.sid, 'uid': s.top.uid, 'id': s.d.id, 'name': s.name, 'hp': g.hp(s), 'damage': s.damage,
        'energy': energy, 'tools': [{'id': t.d.id, 'name': t.name} for t in s.tools],
        'conditions': sorted(s.conditions), 'stack': [c.name for c in s.cards], 'types': g.types(s),
        'retreat': g.retreat_cost(s), 'new': s.turn_entered == g.turn,
    }


def _c(c):
    return {'uid': c.uid, 'id': c.d.id, 'name': c.name}


def game_view(g, viewer='all', ai_eval=None):
    """viewer: 0, 1 ou 'all' (espectador vê as duas mãos)."""
    players = []
    for i, pl in enumerate(g.players):
        show_hand = viewer == 'all' or viewer == i
        players.append({
            'idx': i, 'name': pl.name, 'deck': len(pl.deck), 'prizes': len(pl.prizes),
            'prizes_up': [_c(c) for c in pl.prizes if c.face_up],
            'hand_count': len(pl.hand), 'lost': len(pl.lost_zone),
            'hand': [_c(c) for c in pl.hand] if show_hand else None,
            'discard': [_c(c) for c in pl.discard],
            'active': _slot(g, pl.active) if (g.setup_done or show_hand) else None,
            'bench': [_slot(g, s) for s in pl.bench] if (g.setup_done or show_hand) else [],
            'bench_max': g.bench_max(i),
            'flags': {'energy': pl.energy_attached > 0, 'supporter': pl.supporter_played, 'retreat': pl.retreated},
        })
    prompt = None
    if g.prompt is not None and (viewer == 'all' or viewer == g.prompt.player):
        pr = g.prompt
        prompt = {
            'player': pr.player, 'hint': pr.hint, 'text': pr.text,
            'source': pr.source.name if pr.source is not None and hasattr(pr.source, 'name') else None,
            'options': [{
                'i': i, 'label': o.label, 'kind': o.kind,
                'card': o.card.d.id if o.card is not None and hasattr(o.card, 'd') else None,
                'uid': o.card.uid if o.card is not None and hasattr(o.card, 'uid') else None,
                'target': list(o.target) if o.target else None,
            } for i, o in enumerate(pr.options)],
        }
        if pr.data.get('deck_view'):
            # busca no baralho: todas as cartas (ordem oculta), marcando as que podem ser pegas
            ok = {o.card.d.id for o in pr.options if o.card is not None and hasattr(o.card, 'd')}
            picked = {c.uid for c in pr.data.get('picked', [])}
            prompt['deck_cards'] = sorted(
                ({'id': c.d.id, 'name': c.name, 'eligible': c.d.id in ok, 'picked': c.uid in picked}
                 for c in g.players[pr.player].deck), key=lambda x: (x['name'], x['picked']))
    elif g.prompt is not None:
        prompt = {'player': g.prompt.player, 'hint': g.prompt.hint, 'text': 'Oponente pensando…',
                  'options': [], 'hidden': True}
    return {
        'turn': g.turn, 'current': g.current, 'first_player': g.first_player, 'setup_done': g.setup_done,
        'stadium': {'id': g.stadium.d.id, 'name': g.stadium.name, 'owner': g.stadium.owner} if g.stadium else None,
        'players': players, 'prompt': prompt, 'done': g.done, 'winner': g.winner, 'end_reason': g.end_reason,
        'log': g.log[-400:], 'seed': g.seed, 'decisions': g.decisions, 'ai_eval': ai_eval,
    }
