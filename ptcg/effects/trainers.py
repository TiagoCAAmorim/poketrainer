"""Itens e Apoiadores da rotação H/I/J (escritos à mão a partir do texto oficial)."""
from __future__ import annotations

from ..core import TrainerImpl
from . import lib, register_trainer, trainer
from .lib import card_filter, or_filter


# ------------------------------------------------------------------ utilidades
def others(g, p, card):
    return [c for c in g.players[p].hand if c is not card]


def T_ok(g, card, slot):
    """O efeito deste Treinador pode afetar este Pokémon? (Snow Camouflage, Wide Wall...)"""
    return not g.anyhook('prevent_trainer_effects', card=card, target=slot)


def gust_pred(card, extra=None):
    return lambda g, s: T_ok(g, card, s) and (extra is None or extra(g, s))


def basic(t=None):
    return lambda c: c.d.basic_energy and (t is None or c.d.provides == t)


def is_pokemon(c):
    return c.d.kind == 'pokemon'


def evo_pred(c):
    return c.d.is_evolution


def choose_my_slot(g, p, pred, text, card, bench_only=False):
    pl = g.players[p]
    cands = [s for s in (pl.bench if bench_only else pl.in_play()) if pred(g, s)]
    return (yield from g.choose_slot(p, cands, 'target', text, card))


def opp_choose_slot(g, p, pred, text, card, bench_only=False):
    op = g.players[1 - p]
    cands = [s for s in (op.bench if bench_only else op.in_play()) if pred(g, s) and T_ok(g, card, s)]
    return (yield from g.choose_slot(p, cands, 'opp_target', text, card))


def search_multi(g, p, preds, card, text='Buscar'):
    """'Search your deck for an Item card, a Pokémon Tool card, ...' (um de cada)."""
    pl = g.players[p]
    got = []
    for label, pr in preds:
        c = yield from g.choose_cards(p, [x for x in pl.deck if pr(x) and x not in got], 1, 0, 'search',
                                      f'{text}: {label}', card)
        got += c
    for x in got:
        pl.deck.remove(x)
        pl.hand.append(x)
    g.shuffle(p)
    g.say(f'{pl.name} buscou {", ".join(x.name for x in got) or "nada"}')
    return got


# ====================================================================== ITENS
@trainer('Accompanying Flute')
def _(g, p, card):
    op = g.players[1 - p]
    top = op.deck[:5]
    del op.deck[:len(top)]
    op.limbo.extend(top)
    n = g.bench_space(1 - p)
    got = yield from g.choose_cards(p, [c for c in top if c.d.is_basic], n, 0, 'pick', 'Básicos para o Banco do oponente', card)
    for c in top:
        op.limbo.remove(c)
    for c in got:
        yield from g.play_to_bench(1 - p, c)
    op.deck.extend([c for c in top if c not in got])
    g.shuffle(1 - p)


@trainer("Arven's Sandwich")
def _(g, p, card):
    a = g.players[p].active
    if a:
        g.heal(a, 100 if a.d.family == "Arven's" else 30)


@trainer('Awakening Drum')
def _(g, p, card):
    g.draw(p, sum(1 for s in g.players[p].in_play() if 'ancient' in s.d.tags))


def _blowtorch(g, p, card):
    yield from g.discard_from_hand(p, 1, source=card, pred=basic('R'))
    op = g.players[1 - p]
    opts = []
    targets = [(s, x) for s in op.in_play() for x in s.tools + [e for e in s.energy if e.d.special_energy]
               if T_ok(g, card, s)]
    labels = [f'{x.name} — {g.slot_label(s)}' for s, x in targets]
    if g.stadium is not None:
        labels.append(f'Estádio {g.stadium.name}')
    if not labels:
        return
    i = yield from g.choose_option(p, 'Blowtorch: o que descartar?', labels, source=card)
    if i < len(targets):
        s, x = targets[i]
        (s.tools if x in s.tools else s.energy).remove(x)
        g.players[x.owner].discard.append(x)
    else:
        yield from g.discard_stadium()


register_trainer('Blowtorch', TrainerImpl(run=_blowtorch, can_play=lambda g, p, c: any(
    basic('R')(x) for x in others(g, p, c))))


@trainer('Boxed Order')
def _(g, p, card):
    yield from lib.search_to_hand(g, p, lambda c: c.d.is_item, 2, card)
    g.turn_ended = True


@trainer('Brilliant Blender')
def _(g, p, card):
    pl = g.players[p]
    got = yield from g.choose_cards(p, pl.deck, 5, 0, 'pick', 'Cartas para descartar do baralho', card)
    for c in got:
        pl.deck.remove(c)
        pl.discard.append(c)
    g.shuffle(p)


@trainer('Bug Catching Set')
def _(g, p, card):
    yield from lib.look_top(g, p, 7, lambda c: (c.d.kind == 'pokemon' and 'G' in c.d.types) or basic('G')(c), 2,
                            source=card)


register_trainer('Call Bell', TrainerImpl(
    run=lambda g, p, c: lib.search_to_hand(g, p, lambda x: x.d.is_supporter, 1, c),
    can_play=lambda g, p, c: not g.players[p].went_first and g.first_turn(p)))


def _chill(g, p, card):
    s = yield from opp_choose_slot(g, p, lambda g, s: bool(s.energy), 'Pokémon do oponente', card)
    if s:
        e = yield from g.choose_cards(p, s.energy, 1, 1, 'pick', 'Energia para a mão do oponente', card)
        s.energy.remove(e[0])
        g.players[1 - p].hand.append(e[0])


register_trainer('Chill Teaser Toy', TrainerImpl(run=_chill, can_play=lambda g, p, c: not g.players[p].went_first
                                                 and g.first_turn(p)))


@trainer('Crushing Hammer')
def _(g, p, card):
    if g.flip():
        s = yield from opp_choose_slot(g, p, lambda g, s: bool(s.energy), 'Descartar Energia de', card)
        if s:
            yield from lib.discard_energy_from(g, p, s, 1, source=card)


@trainer('Dangerous Laser')
def _(g, p, card):
    a = g.players[1 - p].active
    if a and T_ok(g, card, a):
        g.add_condition(a, 'burned')
        g.add_condition(a, 'confused')


@trainer('Dark Bell')
def _(g, p, card):
    for q in (p, 1 - p):
        a = g.players[q].active
        if a and not g.has_type(a, 'D') and T_ok(g, card, a):
            g.add_condition(a, 'confused')


@trainer('Deduction Kit')
def _(g, p, card):
    pl = g.players[p]
    top = pl.deck[:3]
    i = yield from g.choose_option(p, 'Deduction Kit', ['Recolocar no topo (em qualquer ordem)',
                                                         'Embaralhar e colocar no fundo'], source=card)
    if i == 1:
        del pl.deck[:len(top)]
        g.rng.shuffle(top)
        pl.deck.extend(top)
    else:
        yield from reorder_top(g, p, len(top), card)


def reorder_top(g, p, n, card):
    pl = g.players[p]
    top = pl.deck[:n]
    del pl.deck[:len(top)]
    pl.limbo.extend(top)
    order = []
    pool = list(top)
    while len(pool) > 1:
        c = yield from g.choose_cards(p, pool, 1, 1, 'order', 'Próxima carta do topo', card, key=lambda x: x.uid)
        order.append(c[0])
        pool.remove(c[0])
    order += pool
    for c in top:
        pl.limbo.remove(c)
    pl.deck[0:0] = order


register_trainer('Dragon Elixir', TrainerImpl(run=lambda g, p, c: g.heal(g.players[p].active, 60),
                                              can_play=lambda g, p, c: g.players[p].active is not None and
                                              g.has_type(g.players[p].active, 'N')))


@trainer('Dusk Ball')
def _(g, p, card):
    yield from lib.look_top(g, p, 7, is_pokemon, 1, source=card, from_bottom=True)


@trainer('Energy Coin')
def _(g, p, card):
    if g.flip() and g.flip():
        yield from lib.search_attach(g, p, basic(), 1, lambda: g.players[p].in_play(), card)
    else:
        g.shuffle(p)


@trainer('Energy Search Pro')
def _(g, p, card):
    pl = g.players[p]
    got = []
    while True:
        types = {c.d.provides for c in got}
        cands = [c for c in pl.deck if c.d.basic_energy and c.d.provides not in types]
        pick = yield from g.choose_cards(p, cands, 1, 0, 'search', 'Energia básica (tipos diferentes)', card)
        if not pick:
            break
        got.append(pick[0])
        pl.deck.remove(pick[0])
        pl.limbo.append(pick[0])
    for c in got:
        pl.limbo.remove(c)
    pl.hand.extend(got)
    g.shuffle(p)


@trainer('Energy Swatter')
def _(g, p, card):
    op = g.players[1 - p]
    lib.reveal_hand(g, 1 - p)
    got = yield from g.choose_cards(p, [c for c in op.hand if c.d.kind == 'energy'], 1, 1, 'pick',
                                    'Energia para o fundo do baralho do oponente', card)
    for c in got:
        op.hand.remove(c)
        op.deck.append(c)


@trainer('Energy Switch')
def _(g, p, card):
    pl = g.players[p]
    yield from lib.move_energy(g, p, lambda: pl.in_play(), lambda: pl.in_play(), 1, basic(), card, min_n=1)


register_trainer('Enhanced Hammer', TrainerImpl(
    run=lambda g, p, c: _discard_opp_energy(g, p, c, lambda e: e.d.special_energy),
    can_play=lambda g, p, c: any(e.d.special_energy for s in g.players[1 - p].in_play() for e in s.energy)))


def _discard_opp_energy(g, p, card, pred=None):
    s = yield from opp_choose_slot(g, p, lambda g, s: any(pred is None or pred(e) for e in s.energy),
                                   'Descartar Energia de', card)
    if s:
        yield from lib.discard_energy_from(g, p, s, 1, pred, source=card)


@trainer('Fighting Gong')
def _(g, p, card):
    yield from lib.search_to_hand(g, p, lambda c: basic('F')(c) or (c.d.is_basic and 'F' in c.d.types), 1, card)


register_trainer('Glass Trumpet', TrainerImpl(
    run=lambda g, p, c: lib.attach_from_discard(g, p, basic(), 2,
                                                lambda: [s for s in g.players[p].bench if g.has_type(s, 'C')], c,
                                                each_once=True),
    can_play=lambda g, p, c: any('tera' in s.d.tags for s in g.players[p].in_play())))


@trainer('Great Haul Net')
def _(g, p, card):
    i = yield from g.choose_option(p, 'Great Haul Net', ['Pokémon de Água', 'Energias de Água básicas', 'Ambos'],
                                   source=card)
    if i in (0, 2):
        yield from lib.recover(g, p, lambda c: is_pokemon(c) and 'W' in c.d.types, 3, 'deck', card)
    if i in (1, 2):
        yield from lib.recover(g, p, basic('W'), 3, 'deck', card)


@trainer('Hand Trimmer')
def _(g, p, card):
    for q in (1 - p, p):
        n = len(g.players[q].hand) - 5
        if n > 0:
            yield from g.discard_from_hand(q, n, source=card)


@trainer('Hole-Digging Shovel')
def _(g, p, card):
    lib.mill(g, p, 2)


@trainer("Hop's Bag")
def _(g, p, card):
    yield from lib.search_to_bench(g, p, lambda c: c.d.is_basic and c.d.family == "Hop's", 2, card)


@trainer('Iron Defender')
def _(g, p, card):
    g.add_effect('Iron Defender', p, {'damage_in': lambda g, src, dmg, ctx, target, active:
                 dmg - 30 if target.owner == p and ctx.player != p and g.has_type(target, 'M') else None},
                 duration='opp_next_turn')


register_trainer('Jumbo Ice Cream', TrainerImpl(
    run=lambda g, p, c: g.heal(g.players[p].active, 80),
    can_play=lambda g, p, c: g.players[p].active is not None and g.energy_count(g.players[p].active) >= 3))


@trainer('Love Ball')
def _(g, p, card):
    names = {s.name for s in g.players[1 - p].in_play()}
    yield from lib.search_to_hand(g, p, lambda c: is_pokemon(c) and c.d.name in names, 1, card)


@trainer('Lumiose Galette')
def _(g, p, card):
    a = g.players[p].active
    if a:
        g.heal(a, 20)
        if a.conditions:
            labels = sorted(a.conditions)
            i = yield from g.choose_option(p, 'Remover qual condição?', labels, source=card)
            a.conditions.discard(labels[i])


@trainer('Meddling Memo')
def _(g, p, card):
    n = g.hand_to_deck(1 - p, bottom=True)
    if n:
        g.draw(1 - p, n)


register_trainer('Megaton Blower', TrainerImpl(run=lambda g, p, c: _megaton(g, p, c)))


def _megaton(g, p, card):
    for s in g.players[1 - p].in_play():
        if not T_ok(g, card, s):
            continue
        g.discard_cards(s.tools)
        s.tools = []
        sp = [e for e in s.energy if e.d.special_energy]
        g.discard_energy(s, sp)
    yield from g.discard_stadium()


@trainer('Ogre\'s Mask')
def _(g, p, card):
    pl = g.players[p]
    inplay = [s for s in pl.in_play() if s.d.is_ex and 'Ogerpon' in s.name]
    disc = [c for c in pl.discard if c.d.is_ex and 'Ogerpon' in c.d.name]
    if not inplay or not disc:
        return
    c = yield from g.choose_cards(p, disc, 1, 1, 'pick', 'Ogerpon do descarte', card)
    s = yield from g.choose_slot(p, inplay, 'target', 'Trocar com qual Ogerpon em jogo?', card)
    old = s.cards.pop()
    pl.discard.remove(c[0])
    s.cards.append(c[0])
    pl.discard.append(old)
    g.say(f'{old.name} foi trocado por {c[0].name}')


register_trainer('Poké Vital A', TrainerImpl(run=lambda g, p, c: _heal_one(g, p, c, 150)))


def _heal_one(g, p, card, n, pred=None):
    s = yield from choose_my_slot(g, p, lambda g, s: s.damage > 0 and (pred is None or pred(g, s)),
                                  'Curar qual Pokémon?', card)
    if s:
        g.heal(s, n)
    return s


register_trainer('Potion', TrainerImpl(run=lambda g, p, c: _heal_one(g, p, c, 30)))


@trainer('Pokégear 3.0')
def _(g, p, card):
    yield from lib.look_top(g, p, 7, lambda c: c.d.is_supporter, 1, source=card)


@trainer('Premium Power Pro')
def _(g, p, card):
    g.add_effect('Premium Power Pro', p, {'damage_out': lambda g, src, dmg, ctx, target:
                 dmg + 30 if ctx.player == p and g.has_type(ctx.attacker, 'F') else None}, duration='this_turn')


register_trainer('Prime Catcher', TrainerImpl(
    run=lambda g, p, c: _prime(g, p, c), can_play=lambda g, p, c: bool(g.players[1 - p].bench)))


def _prime(g, p, card):
    s = yield from lib.gust(g, p, gust_pred(card), card)
    if s is not None and g.players[p].bench:
        yield from lib.switch_own(g, p, card)


@trainer('Rare Candy')
def _(g, p, card):
    pairs = candy_pairs(g, p)
    s2 = yield from g.choose_cards(p, [h for h, _ in pairs], 1, 1, 'candy', 'Rare Candy: Estágio 2', card)
    h = s2[0]
    targets = [s for x, s in pairs if x.d.id == h.d.id]
    s = yield from g.choose_slot(p, targets, 'evolve_target', f'Evoluir qual Pokémon para {h.name}?', card)
    g.players[p].hand.remove(h)
    yield from g.evolve(p, s, h, from_hand=True)


def candy_pairs(g, p):
    pl = g.players[p]
    out = []
    if g.first_turn(p):
        return out
    for h in pl.hand:
        if h.d.kind == 'pokemon' and h.d.stage == 2:
            mids = g.db.named(h.d.evolves_from) if h.d.evolves_from else []
            basics = {m.evolves_from for m in mids}
            for s in pl.in_play():
                if s.d.stage == 0 and s.name in basics and s.turn_entered < g.turn and s.turn_evolved < g.turn \
                        and g.can_play_card(p, h):
                    out.append((h, s))
    return out


TRAINERS_CANDY = register_trainer('Rare Candy', TrainerImpl(run=_, can_play=lambda g, p, c: bool(candy_pairs(g, p))))


@trainer('Redeemable Ticket')
def _(g, p, card):
    pl = g.players[p]
    n = len(pl.prizes)
    g.rng.shuffle(pl.prizes)
    pl.deck.extend(pl.prizes)
    pl.prizes = [pl.deck.pop(0) for _ in range(min(n, len(pl.deck)))]


register_trainer('Repel', TrainerImpl(
    run=lambda g, p, c: lib.opp_switches_out(g, p, c) if T_ok(g, c, g.players[1 - p].active) else None,
    can_play=lambda g, p, c: bool(g.players[1 - p].bench)))


@trainer('Roto-Stick')
def _(g, p, card):
    yield from lib.look_top(g, p, 4, lambda c: c.d.is_supporter, 99, source=card)


@trainer('Scoop Up Cyclone')
def _(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: True, 'Devolver qual Pokémon para a mão?', card)
    if s:
        g.remove_slot(s, to='hand')
        yield from g._promote_if_needed()


register_trainer('Scramble Switch', TrainerImpl(run=lambda g, p, c: _scramble(g, p, c),
                                                can_play=lambda g, p, c: bool(g.players[p].bench)))


def _scramble(g, p, card):
    pl = g.players[p]
    old = pl.active
    s = yield from lib.switch_own(g, p, card)
    if s is not None and old is not None and old.energy:
        yield from lib.move_energy(g, p, lambda: [old], lambda: [pl.active], 99, source=card)


def _secret_box(g, p, card):
    yield from g.discard_from_hand(p, 3, source=card)
    yield from search_multi(g, p, [('Item', lambda c: c.d.is_item), ('Ferramenta', lambda c: c.d.is_tool),
                                   ('Apoiador', lambda c: c.d.is_supporter), ('Estádio', lambda c: c.d.is_stadium)],
                            card, 'Secret Box')


register_trainer('Secret Box', TrainerImpl(run=_secret_box, can_play=lambda g, p, c: len(others(g, p, c)) >= 3))


def _special_red(g, p, card):
    op = g.players[1 - p]
    n = g.hand_to_deck(1 - p, bottom=True)
    if n:
        g.draw(1 - p, 3)


register_trainer('Special Red Card', TrainerImpl(run=_special_red,
                                                 can_play=lambda g, p, c: len(g.players[1 - p].prizes) <= 3))


@trainer('Strange Timepiece', can_play=lambda g, p, c: any(
    s.evolved and g.has_type(s, 'P') for s in g.players[p].in_play()))
def _(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: s.evolved and g.has_type(s, 'P'), 'Desevoluir qual Pokémon?',
                                  card)
    if s:
        while s.evolved:
            g.devolve(s, 'hand')
            if not s.evolved or not (yield from g.yes_no(p, 'Remover mais uma evolução?', source=card)):
                break
        s.turn_evolved = g.turn


register_trainer('Super Potion', TrainerImpl(run=lambda g, p, c: _super_potion(g, p, c)))


def _super_potion(g, p, card):
    s = yield from _heal_one(g, p, card, 60)
    if s and s.energy:
        yield from lib.discard_energy_from(g, p, s, 1, source=card)


register_trainer('Switch', TrainerImpl(run=lambda g, p, c: lib.switch_own(g, p, c),
                                       can_play=lambda g, p, c: bool(g.players[p].bench)))


@trainer('TM Machine')
def _(g, p, card):
    yield from lib.search_to_hand(g, p, lambda c: c.d.is_tool and 'Technical Machine' in c.d.name, 3, card)


@trainer("Team Rocket's Bother-Bot")
def _(g, p, card):
    op = g.players[1 - p]
    if not op.prizes or not op.hand:
        return
    prize = g.rng.choice(op.prizes)
    prize.face_up = True
    h = g.rng.choice(op.hand)
    g.say(f'Prêmio revelado: {prize.name}; carta da mão: {h.name}')
    if (yield from g.yes_no(p, f'Trocar {prize.name} (prêmio) por {h.name} (mão)?', source=card)):
        i = op.prizes.index(prize)
        op.hand.remove(h)
        op.prizes[i] = h
        op.hand.append(prize)
        h.face_up = True


@trainer("Team Rocket's Great Ball")
def _(g, p, card):
    if g.flip():
        pred = lambda c: c.d.is_evolution and c.d.family == "Team Rocket's"
    else:
        pred = lambda c: c.d.is_basic and c.d.family == "Team Rocket's"
    yield from lib.search_to_hand(g, p, pred, 1, card)


@trainer("Team Rocket's Venture Bomb")
def _(g, p, card):
    if g.flip():
        s = yield from opp_choose_slot(g, p, lambda g, s: True, 'Colocar 2 contadores em', card)
        if s:
            g.place_counters(s, 2, 'trainer', by=p)
    elif g.players[p].active:
        g.place_counters(g.players[p].active, 2, 'trainer', by=p)


@trainer('Tool Scrapper')
def _(g, p, card):
    pool = [(s, t) for q in (0, 1) for s in g.players[q].in_play() for t in s.tools if T_ok(g, card, s) or q == p]
    where = {t.uid: s for s, t in pool}
    got = yield from g.choose_cards(p, [t for _, t in pool], 2, 0, 'pick', 'Ferramentas para descartar', card,
                                    key=lambda t: t.uid, labeler=lambda t: f'{t.name} — {g.slot_label(where[t.uid])}')
    for t in got:
        where[t.uid].tools.remove(t)
        g.players[t.owner].discard.append(t)


@trainer('Transformation Tome')
def _(g, p, card):
    pl = g.players[p]
    other = next((c for c in pl.hand if c.name == card.name), None)
    if other is None:
        return
    pl.hand.remove(other)
    pl.discard.append(other)
    disc = [c for c in pl.discard if c.d.is_basic]
    inplay = [s for s in pl.in_play() if s.d.stage == 0 and len(s.cards) == 1]
    if not disc or not inplay:
        return
    c = yield from g.choose_cards(p, disc, 1, 1, 'pick', 'Básico do descarte', card)
    s = yield from g.choose_slot(p, inplay, 'target', 'Trocar com qual Básico em jogo?', card)
    old = s.cards[0]
    pl.discard.remove(c[0])
    s.cards[0] = c[0]
    pl.discard.append(old)


register_trainer('Transformation Tome', TrainerImpl(
    run=_, can_play=lambda g, p, c: sum(1 for x in g.players[p].hand if x.name == c.name) >= 2))


def _ultra(g, p, card):
    yield from g.discard_from_hand(p, 2, source=card)
    yield from lib.search_to_hand(g, p, is_pokemon, 1, card)


register_trainer('Ultra Ball', TrainerImpl(run=_ultra, can_play=lambda g, p, c: len(others(g, p, c)) >= 2))


def _unfair(g, p, card):
    for q in (p, 1 - p):
        g.hand_to_deck(q)
    g.draw(p, 5)
    g.draw(1 - p, 2)


register_trainer('Unfair Stamp', TrainerImpl(run=_unfair, can_play=lambda g, p, c: g.kod_last_turn(p)))

register_trainer('Wondrous Patch', TrainerImpl(
    run=lambda g, p, c: lib.attach_from_discard(g, p, basic('P'), 1,
                                                lambda: [s for s in g.players[p].bench if g.has_type(s, 'P')], c),
    can_play=lambda g, p, c: any(basic('P')(x) for x in g.players[p].discard)))

register_trainer("N's PP Up", TrainerImpl(
    run=lambda g, p, c: lib.attach_from_discard(g, p, basic(), 1,
                                                lambda: [s for s in g.players[p].bench if s.d.family == "N's"], c),
    can_play=lambda g, p, c: any(basic()(x) for x in g.players[p].discard)))

register_trainer('Reboot Pod', TrainerImpl(
    run=lambda g, p, c: lib.attach_from_discard(g, p, basic(), 99,
                                                lambda: [s for s in g.players[p].in_play() if 'future' in s.d.tags],
                                                c, each_once=True)))

register_trainer('Night Stretcher', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, lambda x: is_pokemon(x) or x.d.basic_energy, 1, 'hand', c, min_n=1),
    can_play=lambda g, p, c: any(is_pokemon(x) or x.d.basic_energy for x in g.players[p].discard)))

register_trainer('Max Rod', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, lambda x: is_pokemon(x) or x.d.basic_energy, 5, 'hand', c),
    can_play=lambda g, p, c: any(is_pokemon(x) or x.d.basic_energy for x in g.players[p].discard)))

register_trainer('Miracle Headset', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, lambda x: x.d.is_supporter, 2, 'hand', c),
    can_play=lambda g, p, c: any(x.d.is_supporter for x in g.players[p].discard)))

register_trainer('Energy Retrieval', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, basic(), 2, 'hand', c, min_n=1),
    can_play=lambda g, p, c: any(basic()(x) for x in g.players[p].discard)))

register_trainer('Energy Recycler', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, basic(), 5, 'deck', c),
    can_play=lambda g, p, c: any(basic()(x) for x in g.players[p].discard)))

register_trainer('Sacred Ash', TrainerImpl(
    run=lambda g, p, c: lib.recover(g, p, is_pokemon, 5, 'deck', c),
    can_play=lambda g, p, c: any(is_pokemon(x) for x in g.players[p].discard)))

register_trainer('Energy Search', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, basic(), 1, c)))
register_trainer('Master Ball', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, is_pokemon, 1, c)))
register_trainer('Mega Signal', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, lambda x: x.d.is_mega, 1, c)))
register_trainer('Poké Pad', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: is_pokemon(x) and not x.d.rule_box, 1, c)))
register_trainer('Tera Orb', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: is_pokemon(x) and 'tera' in x.d.tags, 1, c)))
register_trainer('Treasure Tracker', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: x.d.is_tool, 5, c)))
register_trainer('Hyper Aroma', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: is_pokemon(x) and x.d.stage == 1, 3, c)))
register_trainer("Team Rocket's Transceiver", TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: x.d.is_supporter and 'Team Rocket' in x.d.name, 1, c)))
register_trainer('Nest Ball', TrainerImpl(run=lambda g, p, c: lib.search_to_bench(g, p, lambda x: x.d.is_basic, 1, c),
                                          can_play=lambda g, p, c: g.bench_space(p) > 0))
register_trainer('Buddy-Buddy Poffin', TrainerImpl(
    run=lambda g, p, c: lib.search_to_bench(g, p, lambda x: x.d.is_basic and x.d.hp <= 70, 2, c),
    can_play=lambda g, p, c: g.bench_space(p) > 0))
register_trainer('Precious Trolley', TrainerImpl(
    run=lambda g, p, c: lib.search_to_bench(g, p, lambda x: x.d.is_basic, 99, c),
    can_play=lambda g, p, c: g.bench_space(p) > 0))
register_trainer('Poké Ball', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, is_pokemon, 1, c)
                                          if g.flip() else None))


def _catcher(g, p, card):
    if g.flip():
        yield from lib.gust(g, p, gust_pred(card), card)


register_trainer('Pokémon Catcher', TrainerImpl(run=_catcher, can_play=lambda g, p, c: bool(g.players[1 - p].bench)))


@trainer('Hole-Digging Shovel')
def _(g, p, card):
    lib.mill(g, p, 2)


# ====================================================================== APOIADORES
def _az(g, p, card):
    pl = g.players[p]
    old = pl.active
    s = yield from lib.switch_own(g, p, card)
    if s is not None and old is not None and old.d.is_ex:
        g.heal(old, 80)


register_trainer("AZ's Tranquility", TrainerImpl(run=_az, can_play=lambda g, p, c: bool(g.players[p].bench)))


def _acerola(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: True, 'Proteger qual Pokémon?', card)
    if s:
        g.add_effect("Acerola's Mischief", p, {
            'damage_in': lambda g, src, dmg, ctx, target, active, s=s: 0 if target is s and ctx.attacker.d.is_ex else None,
            'prevent_attack_effects': lambda g, src, ctx, target, s=s: target is s and ctx.attacker.d.is_ex},
            target=s, duration='opp_next_turn')


register_trainer("Acerola's Mischief", TrainerImpl(run=_acerola,
                                                   can_play=lambda g, p, c: len(g.players[1 - p].prizes) <= 2))


@trainer('Amarys')
def _(g, p, card):
    g.draw(p, 4)

    def end(g, src, player):
        if player == p and len(g.players[p].hand) >= 5:
            g.discard_hand(p)
            g.say('Amarys: mão descartada')
    g.add_effect('Amarys', p, events={'turn_end': end}, duration='this_turn')


def _anthea(g, p, card):
    def h(g, src, n, slot, taker, by_attack, attacker):
        if taker == p and by_attack and attacker is not None and attacker.d.family == "N's" \
                and slot.owner != p and src.effect.data.get('active_ko', True):
            return n + 3
    g.add_effect('Anthea & Concordia', p, {'prizes': h}, duration='this_turn')


register_trainer('Anthea & Concordia', TrainerImpl(run=_anthea, can_play=lambda g, p, c: {
    "N's Darmanitan", "N's Zoroark ex", "N's Vanilluxe", "N's Klinklang", "N's Reshiram", "N's Zekrom"
} <= {s.name for s in g.players[p].in_play()}))

register_trainer("Bianca's Devotion", TrainerImpl(
    run=lambda g, p, c: _heal_one(g, p, c, 9999, lambda g, s: g.hp_left(s) <= 30)))


@trainer("Billy & O'Nare")
def _(g, p, card):
    g.draw(p, 2)
    if len(g.players[p].hand) >= 10:
        g.draw(p, 2)


@trainer("Black Belt's Training")
def _(g, p, card):
    g.add_effect("Black Belt's Training", p, {'damage_out': lambda g, src, dmg, ctx, target:
                 dmg + 40 if ctx.player == p and target.d.is_ex else None}, duration='this_turn')


register_trainer("Boss's Orders", TrainerImpl(run=lambda g, p, c: lib.gust(g, p, gust_pred(c), c),
                                              can_play=lambda g, p, c: bool(g.players[1 - p].bench)))


def _briar(g, p, card):
    def h(g, src, n, slot, taker, by_attack, attacker):
        if taker == p and by_attack and attacker is not None and 'tera' in attacker.d.tags and slot.owner != p:
            return n + 1
    g.add_effect('Briar', p, {'prizes': h}, duration='this_turn')


register_trainer('Briar', TrainerImpl(run=_briar, can_play=lambda g, p, c: len(g.players[1 - p].prizes) == 2))


@trainer("Brock's Scouting")
def _(g, p, card):
    i = yield from g.choose_option(p, "Brock's Scouting", ['Até 2 Pokémon Básicos', '1 Pokémon de Evolução'],
                                   source=card)
    if i == 0:
        yield from lib.search_to_hand(g, p, lambda c: c.d.is_basic, 2, card)
    else:
        yield from lib.search_to_hand(g, p, evo_pred, 1, card)


def _canari(g, p, card):
    yield from g.discard_from_hand(p, 1, source=card)
    yield from lib.search_to_hand(g, p, lambda c: is_pokemon(c) and 'L' in c.d.types, 4, card)


register_trainer('Canari', TrainerImpl(run=_canari, can_play=lambda g, p, c: len(others(g, p, c)) >= 1))


def _caretaker(g, p, card):
    n = g.draw(p, 2)
    if n and g.stadium is not None and g.stadium.name == 'Community Center':
        pl = g.players[p]
        if card in pl.limbo:
            pl.limbo.remove(card)
            pl.deck.append(card)
            g.shuffle(p)


register_trainer('Caretaker', TrainerImpl(run=_caretaker))
register_trainer('Carmine', TrainerImpl(run=lambda g, p, c: (g.discard_hand(p), g.draw(p, 5)), first_turn_ok=True))


def _cassiopeia(g, p, card):
    yield from lib.search_to_hand(g, p, lambda c: True, 2, card)


register_trainer('Cassiopeia', TrainerImpl(run=_cassiopeia, can_play=lambda g, p, c: len(others(g, p, c)) == 0))
register_trainer('Cheren', TrainerImpl(run=lambda g, p, c: g.draw(p, 3)))
register_trainer('Friends in Paldea', TrainerImpl(run=lambda g, p, c: g.draw(p, 3)))
register_trainer('Urbain', TrainerImpl(run=lambda g, p, c: g.draw(p, 3)))


@trainer("Ciphermaniac's Codebreaking")
def _(g, p, card):
    pl = g.players[p]
    got = yield from g.choose_cards(p, pl.deck, 2, min(2, len(pl.deck)), 'search', 'Cartas para o topo', card)
    for c in got:
        pl.deck.remove(c)
    pl.limbo.extend(got)
    g.shuffle(p)
    order = got
    if len(got) == 2:
        first = yield from g.choose_cards(p, got, 1, 1, 'order', 'Qual fica no topo?', card, key=lambda x: x.uid)
        order = first + [x for x in got if x is not first[0]]
    for c in got:
        pl.limbo.remove(c)
    pl.deck[0:0] = order


register_trainer("Clemont's Quick Wit", TrainerImpl(run=lambda g, p, c: [g.heal(s, 60) for s in g.players[p].in_play()
                                                                        if g.has_type(s, 'L')]))


@trainer("Colress's Tenacity")
def _(g, p, card):
    yield from search_multi(g, p, [('Estádio', lambda c: c.d.is_stadium), ('Energia', lambda c: c.d.kind == 'energy')],
                            card, "Colress's Tenacity")


register_trainer('Cook', TrainerImpl(run=lambda g, p, c: g.heal(g.players[p].active, 70) if g.players[p].active else None))


@trainer('Crispin')
def _(g, p, card):
    pl = g.players[p]
    got = []
    for _ in range(2):
        types = {c.d.provides for c in got}
        pick = yield from g.choose_cards(p, [c for c in pl.deck if c.d.basic_energy and c.d.provides not in types],
                                         1, 0, 'search_energy', 'Crispin: Energia básica (tipos diferentes)', card)
        if not pick:
            break
        got.append(pick[0])
        pl.deck.remove(pick[0])
        pl.limbo.append(pick[0])
    if len(got) == 2:
        h = yield from g.choose_cards(p, got, 1, 1, 'pick', 'Qual vai para a mão?', card)
        pl.limbo.remove(h[0])
        pl.hand.append(h[0])
        rest = [x for x in got if x is not h[0]]
        for x in rest:
            pl.limbo.remove(x)
        yield from lib.attach_cards(g, p, rest, lambda: pl.in_play(), card)
    else:
        for x in got:
            pl.limbo.remove(x)
        pl.hand.extend(got)
    g.shuffle(p)


register_trainer('Cyrano', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, lambda x: x.d.is_ex, 3, c)))


@trainer('Dawn')
def _(g, p, card):
    yield from search_multi(g, p, [('Básico', lambda c: c.d.is_basic),
                                   ('Estágio 1', lambda c: is_pokemon(c) and c.d.stage == 1),
                                   ('Estágio 2', lambda c: is_pokemon(c) and c.d.stage == 2)], card, 'Dawn')


@trainer('Drasna')
def _(g, p, card):
    g.hand_to_deck(p)
    g.draw(p, 8 if g.flip() else 3)


@trainer('Drayton')
def _(g, p, card):
    pl = g.players[p]
    top = pl.deck[:7]
    del pl.deck[:len(top)]
    pl.limbo.extend(top)
    a = yield from g.choose_cards(p, [c for c in top if is_pokemon(c)], 1, 0, 'look', 'Drayton: Pokémon', card)
    b = yield from g.choose_cards(p, [c for c in top if c.d.kind == 'trainer'], 1, 0, 'look', 'Drayton: Treinador', card)
    for c in top:
        pl.limbo.remove(c)
    pl.hand += a + b
    pl.deck += [c for c in top if c not in a + b]
    g.shuffle(p)


@trainer("Emcee's Hype")
def _(g, p, card):
    g.draw(p, 2)
    if len(g.players[1 - p].prizes) <= 3:
        g.draw(p, 2)


@trainer('Emma')
def _(g, p, card):
    lib.reveal_hand(g, 1 - p)
    g.draw(p, sum(1 for c in g.players[1 - p].hand if is_pokemon(c)))


@trainer('Eri')
def _(g, p, card):
    op = g.players[1 - p]
    lib.reveal_hand(g, 1 - p)
    got = yield from g.choose_cards(p, [c for c in op.hand if c.d.is_item], 2, 0, 'pick', 'Itens para descartar', card)
    for c in got:
        op.hand.remove(c)
        op.discard.append(c)


register_trainer("Ethan's Adventure", TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: (is_pokemon(x) and x.d.family == "Ethan's") or basic('R')(x), 3, c)))


@trainer("Explorer's Guidance")
def _(g, p, card):
    yield from lib.look_top(g, p, 6, lambda c: True, 2, rest='discard', source=card, min_take=2)


register_trainer('Fennel', TrainerImpl(run=lambda g, p, c: [g.heal(s, 40) for s in g.players[p].in_play()]))
register_trainer('Firebreather', TrainerImpl(run=lambda g, p, c: lib.search_to_hand(g, p, basic('R'), 7, c)))


def _gladion(g, p, card):
    g.add_effect("Gladion's Final Battle", p, {'damage_out': lambda g, src, dmg, ctx, target:
                 dmg + 80 if ctx.player == p and not ctx.attacker.d.rule_box else None}, duration='this_turn')


register_trainer("Gladion's Final Battle", TrainerImpl(run=_gladion, can_play=lambda g, p, c: len(others(g, p, c)) == 0))


def _grimsley(g, p, card):
    yield from lib.look_top(g, p, 7, lambda c: is_pokemon(c) and 'D' in c.d.types and c.d.is_basic,
                            1 if g.bench_space(p) else 0, dest='bench', rest='bottom', source=card)


register_trainer("Grimsley's Move", TrainerImpl(run=_grimsley, can_play=lambda g, p, c: not g.first_turn(p)))


@trainer('Gwynn', can_play=lambda g, p, c: any(
    is_pokemon(x) and not x.d.rule_box for x in g.players[p].hand))
def _(g, p, card):
    got = yield from g.discard_from_hand(p, 2, source=card, pred=lambda c: is_pokemon(c) and not c.d.rule_box, min_n=0)
    g.draw(p, 3 * len(got))


@trainer('Harlequin')
def _(g, p, card):
    for q in (p, 1 - p):
        g.hand_to_deck(q)
    if g.flip():
        g.draw(p, 5)
        g.draw(1 - p, 3)
    else:
        g.draw(p, 3)
        g.draw(1 - p, 5)


register_trainer('Hassel', TrainerImpl(run=lambda g, p, c: lib.look_top(g, p, 8, lambda x: True, 3, source=c),
                                       can_play=lambda g, p, c: g.kod_last_turn(p)))


@trainer('Hilda')
def _(g, p, card):
    yield from search_multi(g, p, [('Pokémon de Evolução', evo_pred), ('Energia', lambda c: c.d.kind == 'energy')],
                            card, 'Hilda')


def _iris(g, p, card):
    yield from g.discard_from_hand(p, 1, source=card)
    g.draw_until(p, 6)


register_trainer("Iris's Fighting Spirit", TrainerImpl(run=_iris, can_play=lambda g, p, c: len(others(g, p, c)) >= 1))
register_trainer('Jacinthe', TrainerImpl(run=lambda g, p, c: _heal_one(g, p, c, 150, lambda g, s: g.has_type(s, 'P'))))


@trainer("Janine's Secret Art")
def _(g, p, card):
    pl = g.players[p]
    used = []
    for _ in range(2):
        cands = [s for s in pl.in_play() if g.has_type(s, 'D') and s not in used]
        if not cands:
            break
        s = yield from g.choose_slot(p, cands, 'attach_target', 'Pokémon Escuridão (Janine)', card, optional=True)
        if s is None:
            break
        used.append(s)
        e = next((c for c in pl.deck if basic('D')(c)), None)
        if e is not None:
            pl.deck.remove(e)
            yield from g.attach_energy(p, e, s)
            if g.is_active(s):
                g.add_condition(s, 'poisoned')
    g.shuffle(p)


@trainer("Jasmine's Gaze")
def _(g, p, card):
    g.add_effect("Jasmine's Gaze", p, {'damage_in': lambda g, src, dmg, ctx, target, active:
                 dmg - 30 if target.owner == p and ctx.player != p else None}, duration='opp_next_turn')


register_trainer('Jett', TrainerImpl(run=lambda g, p, c: g.draw(p, sum(1 for s in g.players[1 - p].in_play()
                                                                        if s.d.is_mega))))


@trainer('Judge')
def _(g, p, card):
    for q in (p, 1 - p):
        g.hand_to_deck(q)
    g.draw(p, 4)
    g.draw(1 - p, 4)


@trainer('Kieran')
def _(g, p, card):
    i = yield from g.choose_option(p, 'Kieran', ['Trocar seu Ativo', '+30 de dano em Pokémon ex/V Ativo'], source=card)
    if i == 0:
        yield from lib.switch_own(g, p, card)
    else:
        g.add_effect('Kieran', p, {'damage_out': lambda g, src, dmg, ctx, target:
                     dmg + 30 if ctx.player == p and target.d.is_ex else None}, duration='this_turn')


def _kofu(g, p, card):
    pl = g.players[p]
    got = yield from g.choose_cards(p, others(g, p, card), 2, 2, 'bottom', 'Cartas para o fundo do baralho', card)
    for c in got:
        pl.hand.remove(c)
        pl.deck.append(c)
    g.draw(p, 4)


register_trainer('Kofu', TrainerImpl(run=_kofu, can_play=lambda g, p, c: len(others(g, p, c)) >= 2))


@trainer('Lacey')
def _(g, p, card):
    g.hand_to_deck(p)
    g.draw(p, 8 if len(g.players[1 - p].prizes) <= 3 else 4)


register_trainer("Lana's Aid", TrainerImpl(run=lambda g, p, c: lib.recover(
    g, p, lambda x: (is_pokemon(x) and not x.d.rule_box) or x.d.basic_energy, 3, 'hand', c)))


@trainer("Larry's Skill")
def _(g, p, card):
    g.discard_hand(p)
    yield from search_multi(g, p, [('Pokémon', is_pokemon), ('Apoiador', lambda c: c.d.is_supporter),
                                   ('Energia básica', basic())], card, "Larry's Skill")


@trainer("Lillie's Determination")
def _(g, p, card):
    g.hand_to_deck(p)
    g.draw(p, 8 if len(g.players[p].prizes) == 6 else 6)


def _lisia(g, p, card):
    s = yield from lib.gust(g, p, gust_pred(card, lambda g, s: s.d.stage == 0), card)
    if s is not None:
        g.add_condition(s, 'confused')


register_trainer("Lisia's Appeal", TrainerImpl(run=_lisia, can_play=lambda g, p, c: any(
    s.d.stage == 0 for s in g.players[1 - p].bench)))


@trainer("Lt. Surge's Bargain")
def _(g, p, card):
    yes = yield from g.yes_no(1 - p, 'Lt. Surge: cada jogador pega 1 prêmio? (Não: o oponente compra 4)',
                              source=card)
    if yes:
        for q in (p, 1 - p):
            pl = g.players[q]
            if pl.prizes:
                pl.hand.append(pl.prizes.pop(0))
        g._check_win()
    else:
        g.draw(p, 4)


@trainer('Lucian')
def _(g, p, card):
    n = [g.hand_to_deck(q, bottom=True) for q in (p, 1 - p)]
    if any(n):
        for q in (p, 1 - p):
            g.draw(q, 6 if g.flip() else 3)


@trainer("Misty's Vitality")
def _(g, p, card):
    pl = g.players[p]
    s = yield from g.choose_slot(p, pl.in_play(), 'attach_target', 'Ligar Energias de Água em', card)
    got = yield from g.choose_cards(p, [c for c in pl.deck if basic('W')(c)], 4, 0, 'search_energy', 'Energias de Água', card)
    for c in got:
        pl.deck.remove(c)
        yield from g.attach_energy(p, c, s)
    g.shuffle(p)
    g.turn_ended = True


def _morty(g, p, card):
    yield from g.discard_from_hand(p, 1, source=card)
    g.draw(p, len(g.players[1 - p].bench))


register_trainer("Morty's Conviction", TrainerImpl(run=_morty, can_play=lambda g, p, c: len(others(g, p, c)) >= 1))


@trainer("N's Plan")
def _(g, p, card):
    pl = g.players[p]
    yield from lib.move_energy(g, p, lambda: pl.bench, lambda: [pl.active] if pl.active else [], 2, source=card)


def _naveen(g, p, card):
    pl = g.players[p]
    got = yield from g.choose_cards(p, others(g, p, card), len(pl.hand), 0, 'discard', 'Descartar antes de comprar', card)
    for c in got:
        pl.hand.remove(c)
        pl.discard.append(c)
    g.draw_until(p, 5)


register_trainer('Naveen', TrainerImpl(run=_naveen, can_play=lambda g, p, c: bool(g.players[p].deck)))


@trainer('Perrin')
def _(g, p, card):
    pl = g.players[p]
    got = yield from g.choose_cards(p, [c for c in others(g, p, card) if is_pokemon(c)], 2, 0, 'pick',
                                    'Pokémon da mão para o baralho', card)
    for c in got:
        pl.hand.remove(c)
        pl.deck.append(c)
    if got:
        yield from lib.search_to_hand(g, p, is_pokemon, len(got), card)


register_trainer('Philippe', TrainerImpl(run=lambda g, p, c: _philippe(g, p, c)))


def _philippe(g, p, card):
    pl = g.players[p]
    s = yield from choose_my_slot(g, p, lambda g, s: g.has_type(s, 'M'), 'Pokémon Metal', card)
    if s:
        yield from lib.attach_from_discard(g, p, basic('M'), 2, lambda: [s], card)


register_trainer('Picnicker', TrainerImpl(run=lambda g, p, c: g.draw(p, 4 if g.flip() else 2)))


def _pcl(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: s.damage > 0 or bool(s.conditions), 'Curar qual Pokémon?', card)
    if s:
        g.heal(s, 60)
        s.clear_conditions()


register_trainer('Pokémon Center Lady', TrainerImpl(run=_pcl))


@trainer("Professor's Research")
def _(g, p, card):
    g.discard_hand(p)
    g.draw(p, 7)


@trainer('Raifort')
def _(g, p, card):
    pl = g.players[p]
    top = pl.deck[:5]
    del pl.deck[:len(top)]
    pl.limbo.extend(top)
    got = yield from g.choose_cards(p, top, 5, 0, 'pick', 'Raifort: cartas para descartar', card, key=lambda x: x.uid)
    for c in top:
        pl.limbo.remove(c)
    pl.discard += got
    rest = [c for c in top if c not in got]
    pl.deck[0:0] = rest
    if len(rest) > 1:
        yield from reorder_top(g, p, len(rest), card)


def _rosa(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: s.d.stage == 2, 'Pokémon Estágio 2', card)
    if s:
        yield from lib.attach_from_discard(g, p, basic(), 2, lambda: [s], card)


register_trainer("Rosa's Encouragement", TrainerImpl(run=_rosa, can_play=lambda g, p, c: len(g.players[p].prizes) >
                                                     len(g.players[1 - p].prizes)))


@trainer("Roxie's Performance")
def _(g, p, card):
    o = 1 - p
    g.add_effect("Roxie's Performance", p, {'can_retreat': lambda g, src, slot:
                 False if slot.owner == o and 'poisoned' in slot.conditions else None}, duration='opp_next_turn')


@trainer('Ruffian')
def _(g, p, card):
    s = yield from opp_choose_slot(g, p, lambda g, s: bool(s.tools) or any(e.d.special_energy for e in s.energy),
                                   'Pokémon do oponente', card)
    if s:
        if s.tools:
            t = s.tools.pop(0)
            g.players[t.owner].discard.append(t)
        sp = [e for e in s.energy if e.d.special_energy]
        if sp:
            yield from lib.discard_energy_from(g, p, s, 1, lambda e: e.d.special_energy, source=card)


register_trainer('Rust Syndicate Grunt', TrainerImpl(run=lambda g, p, c: _discard_opp_energy(g, p, c),
                                                     can_play=lambda g, p, c: g.kod_last_turn(p)))


@trainer('Salvatore')
def _(g, p, card):
    pl = g.players[p]
    cands = [s for s in pl.in_play() if any(c.d.is_evolution and c.d.evolves_from == s.name and not c.d.abilities
                                            for c in pl.deck)]
    if not cands or g.first_turn(p):
        g.shuffle(p)
        return
    s = yield from g.choose_slot(p, cands, 'evolve_target', 'Evoluir qual Pokémon?', card)
    evo = yield from g.choose_cards(p, [c for c in pl.deck if c.d.is_evolution and c.d.evolves_from == s.name
                                        and not c.d.abilities], 1, 1, 'search', 'Evolução sem Habilidade', card)
    pl.deck.remove(evo[0])
    yield from g.evolve(p, s, evo[0], from_hand=False)
    g.shuffle(p)


def _surfer(g, p, card):
    s = yield from lib.switch_own(g, p, card)
    if s is not None:
        g.draw_until(p, 5)


register_trainer('Surfer', TrainerImpl(run=_surfer, can_play=lambda g, p, c: bool(g.players[p].bench)))
register_trainer('Tarragon', TrainerImpl(run=lambda g, p, c: lib.recover(
    g, p, lambda x: (is_pokemon(x) and 'F' in x.d.types) or basic('F')(x), 4, 'hand', c)))


def _archer(g, p, card):
    for q in (p, 1 - p):
        g.hand_to_deck(q)
    g.draw(p, 5)
    g.draw(1 - p, 3)


register_trainer("Team Rocket's Archer", TrainerImpl(run=_archer, can_play=lambda g, p, c: g.kod_last_turn(
    p, lambda e: e['family'] == "Team Rocket's")))


@trainer("Team Rocket's Ariana")
def _(g, p, card):
    pl = g.players[p]
    allrocket = pl.in_play() and all(s.d.family == "Team Rocket's" for s in pl.in_play())
    g.draw_until(p, 8 if allrocket else 5)


def _giovanni(g, p, card):
    pl = g.players[p]
    cands = [s for s in pl.bench if s.d.family == "Team Rocket's"]
    if not cands:
        return
    s = yield from g.choose_slot(p, cands, 'switch', 'Novo Ativo (Team Rocket)', card)
    yield from g.switch_active(p, s)
    yield from lib.gust(g, p, gust_pred(card), card)


register_trainer("Team Rocket's Giovanni", TrainerImpl(run=_giovanni, can_play=lambda g, p, c: g.players[p].active is not None
                                                       and g.players[p].active.d.family == "Team Rocket's"
                                                       and any(s.d.family == "Team Rocket's" for s in g.players[p].bench)))
register_trainer("Team Rocket's Petrel", TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: x.d.kind == 'trainer', 1, c)))
register_trainer("Team Rocket's Proton", TrainerImpl(run=lambda g, p, c: lib.search_to_hand(
    g, p, lambda x: x.d.is_basic and x.d.family == "Team Rocket's", 3, c), first_turn_ok=True))


@trainer('Tyme')
def _(g, p, card):
    pl = g.players[p]
    pk = [c for c in others(g, p, card) if is_pokemon(c)]
    if not pk:
        return
    c = yield from g.choose_cards(p, pk, 1, 1, 'pick', 'Tyme: Pokémon escondido', card)
    real = c[0].d.hp
    guesses = sorted({x for x in range(30, 360, 10)} & {real, real - 10, real + 10, real - 20, real + 20, 60, 70, 120})
    opt = yield from g.ask(1 - p, 'guess', f'Tyme: adivinhe o HP de {c[0].name}',
                           [__import__('ptcg.core', fromlist=['Option']).Option(str(h), h, 'text') for h in guesses],
                           card)
    if opt.value == real:
        g.draw(1 - p, 4)
    else:
        g.draw(p, 4)


@trainer('Waitress')
def _(g, p, card):
    pl = g.players[p]
    top = pl.deck[:6]
    del pl.deck[:len(top)]
    pl.limbo.extend(top)
    e = yield from g.choose_cards(p, [c for c in top if c.d.basic_energy], 1, 0, 'look', 'Energia para ligar', card)
    for c in top:
        pl.limbo.remove(c)
    pl.deck += [c for c in top if c not in e]
    if e:
        pl.limbo.append(e[0])
        s = yield from g.choose_slot(p, pl.in_play(), 'attach_target', f'Ligar {e[0].name} em', card)
        pl.limbo.remove(e[0])
        yield from g.attach_energy(p, e[0], s)
    g.shuffle(p)


@trainer("Wally's Compassion")
def _(g, p, card):
    s = yield from choose_my_slot(g, p, lambda g, s: s.d.is_mega and s.damage > 0, 'Curar qual Mega ex?', card)
    if s and g.heal(s, 9999):
        pl = g.players[p]
        pl.hand += s.energy
        s.energy = []


@trainer("Xerosic's Machinations")
def _(g, p, card):
    n = len(g.players[1 - p].hand) - 3
    if n > 0:
        yield from g.discard_from_hand(1 - p, n, source=card)
