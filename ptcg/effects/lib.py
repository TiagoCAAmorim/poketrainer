"""Blocos de construção de efeitos (usados pelo compilador de texto e pelos efeitos escritos à mão).

Convenção: funções que pedem decisões são generators (use `yield from`).
`E` é o contexto de execução de um efeito compilado (ver compiler.Exec).
"""
from __future__ import annotations

import re

from ..core import ANY, COND_NAMES, ENERGY_TYPES, NAME_TO_TYPE, TYPE_NAMES

TYPE_WORDS = '|'.join(['Grass', 'Fire', 'Water', 'Lightning', 'Psychic', 'Fighting', 'Darkness', 'Metal',
                       'Dragon', 'Colorless'])
NUM_WORDS = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
             'eight': 8, 'nine': 9, 'ten': 10, 'any number of': 99, 'any amount of': 99, 'all': 99}


def num(s, default=1):
    if s is None:
        return default
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return NUM_WORDS.get(s, default)


# ============================================================== filtros de cartas
def card_filter(phrase: str, g=None, p=None):
    """Converte frases como 'Basic Fire Energy card', 'Basic Pokémon with 70 HP or less',
    'Pokémon that doesn't have a Rule Box', "Ethan's Pokémon", 'Item card' em predicado(Card)."""
    s = phrase.strip()
    s = re.sub(r'\bcards?\b', '', s).strip()
    s = re.sub(r'\s+', ' ', s)
    preds = []

    m = re.search(r'with (\d+) HP or less', s)
    if m:
        hp = int(m.group(1))
        preds.append(lambda c, hp=hp: c.d.kind == 'pokemon' and c.d.hp <= hp)
        s = s.replace(m.group(0), '').strip()
    if re.search(r"(that )?(doesn't|does not|don't) have a Rule Box", s):
        preds.append(lambda c: c.d.kind == 'pokemon' and not c.d.rule_box)
        s = re.sub(r"(that )?(doesn't|does not|don't) have a Rule Box", '', s).strip()
    m = re.search(r'that (?:has|have) "([^"]+)" in (?:its|their) name', s)
    if m:
        part = m.group(1)
        preds.append(lambda c, part=part: part in c.d.name)
        s = s.replace(m.group(0), '').strip()
    if 'that has no Abilities' in s or 'that have no Abilities' in s:
        preds.append(lambda c: not c.d.abilities)
        s = s.replace('that has no Abilities', '').replace('that have no Abilities', '').strip()
    m = re.match(r"^(Team Rocket's|[A-Z][\w.\-]*'s)\s+(.*)$", s)
    if m and m.group(1) not in ("opponent's",):
        fam = m.group(1)
        preds.append(lambda c, fam=fam: c.d.family == fam)
        s = m.group(2)

    words = s.split()
    want_kind = None
    if 'Energy' in s:
        want_kind = 'energy'
        if 'Basic' in words:
            preds.append(lambda c: c.d.basic_energy)
        elif 'Special' in words:
            preds.append(lambda c: c.d.special_energy)
        for t in re.findall(TYPE_WORDS, s):
            code = NAME_TO_TYPE[t]
            preds.append(lambda c, code=code: c.d.provides == code)
    elif ('Pokémon' in s or 'Pokemon' in s) and 'Tool' not in s:   # ruling 2051: "Pokémon Tool" é Treinador
        want_kind = 'pokemon'
        if re.search(r'\bBasic\b', s):
            preds.append(lambda c: c.d.is_basic)
        if 'Evolution' in s:
            preds.append(lambda c: c.d.is_evolution)
        if 'Stage 1' in s:
            preds.append(lambda c: c.d.kind == 'pokemon' and c.d.stage == 1)
        if 'Stage 2' in s:
            preds.append(lambda c: c.d.kind == 'pokemon' and c.d.stage == 2)
        if 'Mega Evolution' in s:
            preds.append(lambda c: c.d.is_mega)
        elif re.search(r'\bex\b', s):
            preds.append(lambda c: c.d.is_ex)
        if 'Tera' in s:
            preds.append(lambda c: 'tera' in c.d.tags)
        if 'Ancient' in s:
            preds.append(lambda c: 'ancient' in c.d.tags)
        if 'Future' in s:
            preds.append(lambda c: 'future' in c.d.tags)
        types = re.findall(TYPE_WORDS, s)
        if types:
            codes = {NAME_TO_TYPE[t] for t in types}
            preds.append(lambda c, codes=codes: bool(set(c.d.types) & codes))
    elif 'Supporter' in s:
        want_kind = 'trainer'
        preds.append(lambda c: c.d.subtype == 'supporter')
    elif 'Item' in s:
        want_kind = 'trainer'
        preds.append(lambda c: c.d.subtype == 'item')
    elif 'Pokémon Tool' in s or 'Tool' in s:
        want_kind = 'trainer'
        preds.append(lambda c: c.d.subtype == 'tool')
    elif 'Stadium' in s:
        want_kind = 'trainer'
        preds.append(lambda c: c.d.subtype == 'stadium')
    elif 'Trainer' in s:
        want_kind = 'trainer'
    if want_kind:
        preds.insert(0, lambda c, k=want_kind: c.d.kind == k)

    def pred(c):
        return all(f(c) for f in preds)
    return pred


def or_filter(phrase):
    """'Pokémon or Basic Energy card' → predicado."""
    parts = re.split(r'\s+or\s+|,\s*', phrase)
    fs = [card_filter(x) for x in parts if x.strip()]
    return lambda c: any(f(c) for f in fs)


def slot_filter(phrase: str):
    """Predicado(g, slot) para frases como 'Benched Basic Pokémon', 'Fire Pokémon', 'Pokémon ex'."""
    s = phrase
    preds = []
    for t in re.findall(TYPE_WORDS, s):
        code = NAME_TO_TYPE[t]
        preds.append(lambda g, sl, code=code: g.has_type(sl, code))
    if re.search(r'\bBasic\b', s):
        preds.append(lambda g, sl: sl.d.stage == 0)
    if re.search(r'(?<!Mega )Evolution', s) or 'evolved' in s:   # "Mega Evolution ex" pode ser Básico
        preds.append(lambda g, sl: sl.d.stage > 0)
    if 'Stage 2' in s:
        preds.append(lambda g, sl: sl.d.stage == 2)
    if 'Stage 1' in s:
        preds.append(lambda g, sl: sl.d.stage == 1)
    if 'Mega Evolution' in s:
        preds.append(lambda g, sl: sl.d.is_mega)
    elif re.search(r'\bex\b', s):
        preds.append(lambda g, sl: sl.d.is_ex)
    if 'Tera' in s:
        preds.append(lambda g, sl: 'tera' in sl.d.tags)
    if 'Ancient' in s:
        preds.append(lambda g, sl: 'ancient' in sl.d.tags)
    if 'Future' in s:
        preds.append(lambda g, sl: 'future' in sl.d.tags)
    if "Rule Box" in s and ("doesn't" in s or "don't" in s):
        preds.append(lambda g, sl: not sl.d.rule_box)
    m = re.search(r"(Team Rocket's|[A-Z][\w.\-]*'s) Pokémon", s)
    if m and not m.group(1).startswith(('opponent', 'your')):
        fam = m.group(1)
        preds.append(lambda g, sl, fam=fam: sl.d.family == fam)
    return lambda g, sl: all(f(g, sl) for f in preds)


# ============================================================== ações básicas
def search_to_hand(g, p, pred, n, source=None, text='Buscar no baralho', min_n=0):
    found = yield from g.search_deck(p, pred, n, 'search', text, source, min_n=min_n)
    g.players[p].hand.extend(found)
    return found


def search_to_bench(g, p, pred, n, source=None, text='Colocar no Banco'):
    n = min(n, g.bench_space(p))
    if n <= 0:
        g.shuffle(p)
        return []
    found = yield from g.search_deck(p, pred, n, 'search_bench', text, source)
    for c in found:
        yield from g.play_to_bench(p, c)
    return found


def attach_cards(g, p, cards, slots_fn, source=None, text='Ligar em', each_once=False):
    """Liga cada carta de Energia (já removida da zona de origem) a um Pokémon escolhido."""
    pl = g.players[p]
    pl.limbo.extend(cards)
    used = set()
    for c in cards:
        slots = [s for s in slots_fn() if not (each_once and s.sid in used) and g.can_attach_energy(p, c, s)]
        if not slots:
            pl.limbo.remove(c)
            pl.hand.append(c)   # sem alvo válido: a carta fica na mão
            continue
        s = yield from g.choose_slot(p, slots, 'attach_target', f'{text}: {c.name}', source,
                                     energy=c.d.provides)
        pl.limbo.remove(c)
        used.add(s.sid)
        yield from g.attach_energy(p, c, s, from_hand=False)
    return cards


def search_attach(g, p, pred, n, slots_fn, source=None, text='Buscar Energia para ligar', each_once=False):
    pl = g.players[p]
    found = yield from g.choose_cards(p, [c for c in pl.deck if pred(c)], n, 0, 'search_energy', text, source)
    for c in found:
        pl.deck.remove(c)
    yield from attach_cards(g, p, found, slots_fn, source, each_once=each_once)
    g.shuffle(p)
    return found


def attach_from_discard(g, p, pred, n, slots_fn, source=None, text='Energia do descarte', each_once=False):
    pl = g.players[p]
    found = yield from g.choose_cards(p, [c for c in pl.discard if pred(c)], n, 0, 'pick_energy', text, source)
    for c in found:
        pl.discard.remove(c)
    yield from attach_cards(g, p, found, slots_fn, source, each_once=each_once)
    return found


def recover(g, p, pred, n, dest='hand', source=None, text='Recuperar do descarte', min_n=0):
    pl = g.players[p]
    got = yield from g.choose_cards(p, [c for c in pl.discard if pred(c)], n, min_n, 'recover', text, source)
    for c in got:
        pl.discard.remove(c)
        (pl.hand if dest == 'hand' else pl.deck).append(c)
    if dest == 'deck':
        g.shuffle(p)
    if got:
        g.say(f'{pl.name} recuperou {", ".join(c.name for c in got)}')
    return got


def look_top(g, p, n, pred, take_max, dest='hand', rest='shuffle', source=None, text='Olhar o topo',
             min_take=0, from_bottom=False):
    """Olha n cartas do topo (ou fundo), pega até take_max que satisfaçam pred."""
    pl = g.players[p]
    cards = pl.deck[-n:] if from_bottom else pl.deck[:n]
    for c in cards:
        pl.deck.remove(c)
    pl.limbo.extend(cards)
    got = yield from g.choose_cards(p, [c for c in cards if pred(c)], take_max, min_take, 'look', text, source,
                                    key=lambda c: c.d.id)
    for c in cards:
        pl.limbo.remove(c)
    others = [c for c in cards if c not in got]
    for c in got:
        if dest == 'hand':
            pl.hand.append(c)
        elif dest == 'bench':
            yield from g.play_to_bench(p, c)
        elif dest == 'discard':
            pl.discard.append(c)
    if rest == 'shuffle':
        pl.deck.extend(others)
        g.shuffle(p)
    elif rest == 'bottom':
        g.rng.shuffle(others)
        pl.deck.extend(others)
    elif rest == 'discard':
        pl.discard.extend(others)
    elif rest == 'top':
        pl.deck[0:0] = others
    return got


def switch_own(g, p, source=None, text='Escolha o novo Ativo', defer=None):
    pl = g.players[p]
    if not pl.bench or pl.active is None:
        return None
    s = yield from g.choose_slot(p, pl.bench, 'switch', text, source)
    yield from g.switch_active(p, s, defer=defer)
    g.say(f'{pl.name} trocou para {s.name}')
    return s


def gust(g, p, pred=None, source=None, text='Trazer Pokémon do Banco do oponente para o Ativo', blocked_ok=False):
    """blocked_ok: alvos que `pred` recusa ainda podem ser escolhidos, mas nada acontece com eles (ruling 2154)."""
    op = g.players[1 - p]
    cands = [s for s in op.bench if blocked_ok or pred is None or pred(g, s)]
    if not cands or op.active is None:
        return None
    s = yield from g.choose_slot(p, cands, 'gust', text, source)
    if pred is not None and not pred(g, s):
        g.say(f'{s.name} não foi afetado')
        return None
    yield from g.switch_active(1 - p, s, cause='gust')
    g.say(f'{s.name} foi trazido para o Ativo do oponente')
    return s


def opp_switches_out(g, p, source=None):
    """'Switch out your opponent's Active Pokémon to the Bench' (o oponente escolhe)."""
    op = g.players[1 - p]
    if not op.bench or op.active is None:
        return None
    s = yield from g.choose_slot(1 - p, op.bench, 'promote', 'Escolha seu novo Pokémon Ativo', source)
    yield from g.switch_active(1 - p, s, cause='forced')
    return s


def heal_slot(g, slot, n):
    return g.heal(slot, n)


def discard_energy_from(g, chooser, slot, n=1, pred=None, ctx=None, source=None, text='Descartar Energia',
                        units=False):
    """Descarta n Energias de `slot` (escolhidas por `chooser`).

    units=True: conta Energia provida, não cartas (custo do próprio ataque: "Descarte 2 Energias deste
    Pokémon" é satisfeito por uma carta que provê 2+ Energias, como no jogo oficial)."""
    if units:
        chosen = yield from g.choose_energy_to_discard(chooser, slot, n, text=text, source=source, pred=pred)
        return g.discard_energy(slot, chosen, ctx)
    cands = [e for e in slot.energy if pred is None or pred(e)]
    if n >= len(cands):
        chosen = cands
    else:
        chosen = yield from g.choose_cards(chooser, cands, n, n, 'discard_energy', text, source,
                                           key=lambda c: c.d.id)
    return g.discard_energy(slot, chosen, ctx)


def move_energy(g, p, from_slots, to_slots, n=1, pred=None, source=None, text='Mover Energia', min_n=0):
    """Move até n Energias de algum Pokémon de from_slots para algum de to_slots."""
    moved = 0
    for _ in range(n):
        pool = [(s, e) for s in from_slots() for e in s.energy if pred is None or pred(e)]
        if not pool:
            break
        where = {e.uid: s for s, e in pool}
        picks = yield from g.choose_cards(p, [e for _, e in pool], 1, 1 if moved < min_n else 0, 'move_energy',
                                          text, source, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {g.slot_label(where[e.uid])}')
        if not picks:
            break
        e = picks[0]
        src = where[e.uid]
        targets = [s for s in to_slots() if s is not src]
        if not targets:
            break
        t = yield from g.choose_slot(p, targets, 'attach_target', f'Mover {e.name} para', source,
                                     energy=e.d.provides)
        src.energy.remove(e)
        t.energy.append(e)
        g.say(f'{e.name} movida de {src.name} para {t.name}')
        moved += 1
    return moved


def distribute_counters(g, p, n, slots_fn, kind='attack', ctx=None, source=None, text='Colocar contador'):
    """'Put N damage counters on ... in any way you like' (um por vez)."""
    for i in range(n):
        slots = list(slots_fn())
        if not slots:
            break
        s = yield from g.choose_slot(p, slots, 'counters', f'{text} {i + 1}/{n}', source)
        g.place_counters(s, 1, kind, by=p, ctx=ctx)


def bench_damage(g, ctx, n_targets, amount, side='opp', text='Escolha o alvo'):
    """'This attack also does N damage to K of your opponent's Benched Pokémon.'"""
    pl = g.players[ctx.opp if side == 'opp' else ctx.player]
    if n_targets >= 99:
        for s in list(pl.bench):
            g.deal_attack_damage(ctx, s, amount)
        return
    chosen = []
    for _ in range(min(n_targets, len(pl.bench))):
        cands = [s for s in pl.bench if s not in chosen]
        if not cands:
            break
        s = yield from g.choose_slot(ctx.player, cands, 'bench_target', text, ctx.attacker.top)
        chosen.append(s)
    for s in chosen:
        g.deal_attack_damage(ctx, s, amount)


def reveal_hand(g, p):
    pl = g.players[p]
    g.say(f'{pl.name} revelou a mão: {", ".join(c.name for c in pl.hand) or "vazia"}')


def opp_discards_random(g, p, n=1):
    op = g.players[1 - p]
    out = []
    for _ in range(n):
        if not op.hand:
            break
        c = g.rng.choice(op.hand)
        op.hand.remove(c)
        op.discard.append(c)
        out.append(c)
    if out:
        g.say(f'{op.name} descartou {", ".join(c.name for c in out)} (aleatório)')
    return out


def mill(g, p, n):
    pl = g.players[p]
    cards = pl.deck[:n]
    del pl.deck[:len(cards)]
    pl.discard.extend(cards)
    if cards:
        g.say(f'{pl.name} descartou do topo: {", ".join(c.name for c in cards)}')
        if g.current != p:   # Startling Drop (Ferrothorn): descartado do baralho por efeito do oponente
            for c in cards:
                if any(a.name == 'Startling Drop' for a in c.d.abilities):
                    mill(g, 1 - p, 8)
    return cards


def energy_types_of(g, slot):
    out = set()
    for _, units in g.energy_units(slot):
        for u in units:
            out |= set(u)
    return out & set(ENERGY_TYPES)


def cond_word(w):
    return COND_NAMES.get(w.strip().capitalize())
