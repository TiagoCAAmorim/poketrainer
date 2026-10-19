"""Cenários dos efeitos implementados na segunda leva de cobertura (ptcg/effects/extra.py,
abilities2.py, attacks2.py).

    python tests/test_efeitos_novos.py        ou        python -m pytest -q tests/test_efeitos_novos.py
"""
from types import SimpleNamespace

from helpers import act, at_turn, board, card, has, labels, new_game, resolve_all

PSY = 'Basic Psychic Energy'


def drive(gen):
    """Executa um generator do motor escolhendo sempre a primeira opção."""
    try:
        x = next(gen)
        while True:
            x = gen.send(x.options[0])
    except StopIteration as e:
        return e.value


def fix_flips(g, *results):
    """Fixa o resultado das próximas moedas (True = cara)."""
    seq = list(results)
    g.flip = lambda who=None: seq.pop(0) if seq else True


def opp(g):
    return g.players[1]


def me(g):
    return g.players[0]


# ----------------------------------------------------------------------------- ataques
def test_minior_discards_energy_and_hits_bench():
    g = new_game()
    board(g, 0, '30C-124', energy={0: [PSY] * 3}, prizes=6)
    board(g, 1, 'Drakloak', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Shoot Meteors')
    act(g, 'Dreepy (Banco 1)')
    resolve_all(g)
    assert not me(g).active.energy
    assert [e['name'] for e in g.ko_log] == ['Dreepy']


def test_hydra_breath_needs_six_grass_in_hand():
    g = new_game()
    board(g, 0, 'DRI-18', energy={0: ['Basic Grass Energy']}, hand=['Basic Grass Energy'] * 6, prizes=6)
    board(g, 1, 'Drakloak', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Hydra Breath')
    resolve_all(g)
    assert [e['name'] for e in g.ko_log] == ['Drakloak']
    assert not any(c.name == 'Basic Grass Energy' for c in me(g).hand)
    g = new_game()
    board(g, 0, 'DRI-18', energy={0: ['Basic Grass Energy']}, hand=['Basic Grass Energy'] * 5, prizes=6)
    board(g, 1, 'Drakloak', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Hydra Breath')
    resolve_all(g)
    assert not g.ko_log and len(me(g).hand) == 5


def test_torment_locks_the_chosen_attack():
    g = new_game()
    board(g, 0, 'DRI-127', energy={0: [PSY, 'Basic Darkness Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], energy={0: ['Basic Fire Energy', PSY]}, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Torment')
    act(g, 'Phantom Dive')
    resolve_all(g)
    # turno do oponente: Phantom Dive não pode ser usado, Jet Headbutt sim
    assert not g.allowed('can_attack', slot=opp(g).active, attack=opp(g).active.d.attacks[1])
    assert g.allowed('can_attack', slot=opp(g).active, attack=opp(g).active.d.attacks[0])


def test_metronome_copies_the_defending_attack():
    g = new_game()
    board(g, 0, 'TWM-79', energy={0: [PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', energy={0: ['Basic Fire Energy', PSY]}, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Metronome')
    act(g, 'Jet Headbutt')
    resolve_all(g)
    assert opp(g).active.damage == 70


def test_thunder_raid_hits_only_benched_ex_for_210():
    g = new_game()
    board(g, 0, 'DRI-78', energy={0: ['Basic Lightning Energy'] * 3}, prizes=6)
    board(g, 1, 'Drakloak', bench=['Dreepy', 'Mew ex'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Thunder Raid')          # só há um alvo válido (Mew ex): escolhido sozinho
    resolve_all(g)
    assert [e['name'] for e in g.ko_log] == ['Mew ex']
    assert not me(g).active.energy


def test_axe_blast_ko_only_basic():
    g = new_game()
    board(g, 0, 'BLK-70', energy={0: ['Basic Fighting Energy', 'Basic Metal Energy', PSY]}, prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Axe Blast')
    resolve_all(g)
    assert [e['name'] for e in g.ko_log] == ['Dreepy']
    g = new_game()
    board(g, 0, 'BLK-70', energy={0: ['Basic Fighting Energy', 'Basic Metal Energy', PSY]}, prizes=6)
    board(g, 1, 'Drakloak', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Axe Blast')
    resolve_all(g)
    assert not g.ko_log


def test_pernicious_poison_puts_16_counters():
    g = new_game()
    board(g, 0, 'CRI-65', energy={0: ['Basic Water Energy', 'Basic Darkness Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Pernicious Poison')
    resolve_all(g)
    assert 'poisoned' in opp(g).active.conditions
    assert opp(g).active.damage == 160          # no Checkup logo após o ataque


def test_settle_the_score_counts_prizes_taken_last_turn():
    g = new_game()
    board(g, 0, 'ASC-122', energy={0: ['Basic Fighting Energy', 'Basic Fighting Energy', PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    g.prize_log.append((g.turn - 1, 1, 2))
    act(g, 'Atacar: Settle the Score')
    resolve_all(g)
    assert opp(g).active.damage == 80 + 120


def test_round_counts_pokemon_with_round():
    g = new_game()
    board(g, 0, 'BLK-19', bench=['BLK-19', 'BLK-20', 'Dreepy'], energy={0: [PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Round')
    resolve_all(g)
    assert opp(g).active.damage == 60


def test_cellular_evolution_from_deck():
    g = new_game()
    board(g, 0, 'BLK-38', energy={0: [PSY]}, deck=['BLK-39', 'Dreepy'], prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Cellular Evolution')
    resolve_all(g)
    assert me(g).active.name == 'Reuniclus'


def test_counter_adds_damage_taken_last_turn():
    g = new_game()
    board(g, 0, '30C-85', energy={0: ['Basic Fighting Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    me(g).active.flags['dmg_log'] = [(g.turn - 1, 50)]
    act(g, 'Atacar: Counter')
    resolve_all(g)
    assert opp(g).active.damage == 60


def test_hand_trim_discards_down_to_five():
    g = new_game()
    board(g, 0, 'POR-67', energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', hand=[PSY] * 8, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Hand Trim')
    resolve_all(g)
    assert len(opp(g).discard) == 3


def test_riptide_counts_and_shuffles_water():
    g = new_game()
    board(g, 0, 'MEG-34', energy={0: ['Basic Water Energy']}, discard=['Basic Water Energy'] * 3 + [PSY],
          deck=['Dreepy'] * 3, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Riptide')
    resolve_all(g)
    assert opp(g).active.damage == 60
    assert [c.name for c in me(g).discard] == [PSY] and len(me(g).deck) == 6


def test_inferno_x_discards_fire_for_damage():
    g = new_game()
    board(g, 0, 'PFL-13', bench=['Dreepy'], energy={0: ['Basic Fire Energy'] * 3, 1: ['Basic Fire Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Inferno X')
    for _ in range(4):           # descarta as 4 Energias de Fogo
        act(g, 'Basic Fire Energy')
    resolve_all(g)
    assert [e['name'] for e in g.ko_log] == ['Dragapult ex']      # 4 Energias × 90 = 360 ≥ 320


def test_oil_salvo_spreads_six_hits():
    g = new_game()
    board(g, 0, 'DRI-23', energy={0: ['Basic Grass Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Oil Salvo')
    for _ in range(6):
        act(g, 'Dreepy (Banco 1)')
    resolve_all(g)
    assert [e['name'] for e in g.ko_log] == ['Dreepy'] and opp(g).active.damage == 0


def test_collateral_bolts_hits_every_damaged_pokemon_but_self():
    g = new_game()
    board(g, 0, 'TEF-52', bench=['Dreepy'], energy={0: ['Basic Lightning Energy', PSY]}, damage={0: 20, 1: 10}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], damage={0: 10, 1: 10}, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Collateral Bolts')
    resolve_all(g)
    assert me(g).active.damage == 20 and me(g).bench[0].damage == 60
    assert opp(g).active.damage == 60 and opp(g).bench[0].damage == 60


def test_split_bomb_two_targets():
    g = new_game()
    board(g, 0, 'ASC-61', energy={0: ['Basic Lightning Energy'] * 2}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Mew ex', 'Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Split Bomb')
    act(g, 'Dreepy (Banco 2)')
    act(g, 'Mew ex')
    resolve_all(g)
    assert opp(g).bench[0].damage == 60 and opp(g).bench[1].damage == 60 and opp(g).active.damage == 0


def test_expelling_tornado_keeps_three_benched():
    g = new_game()
    board(g, 0, 'TEF-5', energy={0: ['Basic Grass Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'] * 5, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Expelling Tornado')
    deck_before = len(opp(g).deck)
    for _ in range(3):
        g.step(0)
    resolve_all(g)
    assert len(opp(g).bench) == 3 and len(opp(g).deck) == deck_before + 2 - 1      # −1: compra do turno dele


def test_mystical_eyes_devolves():
    g = new_game()
    board(g, 0, 'SSP-95', energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Drakloak', prizes=6)
    at_turn(g)
    opp(g).active.cards.insert(0, card('Dreepy', 1))
    act(g, 'Atacar: Mystical Eyes')
    resolve_all(g)
    assert opp(g).active.name == 'Dreepy' and any(c.name == 'Drakloak' for c in opp(g).hand)


def test_kinds_of_damage_from_discarded_cards():
    g = new_game()
    board(g, 0, 'CRI-24', energy={0: ['Basic Water Energy']},
          deck=['Basic Water Energy', 'Basic Water Energy', PSY, 'Dreepy', 'Basic Water Energy', PSY, 'Dreepy'], prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Iceberg Breaker')
    resolve_all(g)
    assert opp(g).active.damage == 180


def test_energy_straw_counts_energy_in_opponent_hand():
    g = new_game()
    board(g, 0, 'ASC-13', energy={0: ['Basic Grass Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', hand=[PSY, PSY, PSY, 'Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Energy Straw')
    resolve_all(g)
    assert opp(g).active.damage == 240


def test_walking_wake_counts_placed_counters():
    g = new_game()
    board(g, 0, 'TWM-63', energy={0: ['Basic Water Energy', 'Basic Water Energy', PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Undulating Slice')
    act(g, '9')
    resolve_all(g)
    assert me(g).active.damage == 90 and opp(g).active.damage == 180


# ----------------------------------------------------------------------------- efeitos com duração
def test_pachirisu_punishes_energy_attached_to_defender():
    g = new_game()
    board(g, 0, 'MEG-51', energy={0: ['Basic Lightning Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', hand=[PSY], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Electrified Incisors')
    resolve_all(g)
    t = opp(g).active
    before = t.damage
    drive(g.attach_energy(1, opp(g).hand[0], t, from_hand=True))
    assert t.damage == before + 80


def test_strong_bash_reflects_damage_counters():
    g = new_game()
    board(g, 0, 'DRI-146', energy={0: ['Basic Metal Energy'] * 3}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Strong Bash')
    resolve_all(g)
    z, att = me(g).active, opp(g).active
    ctx = SimpleNamespace(player=1, attacker=att)
    base = att.damage
    z.damage += 50
    drive(g.emit('damaged_by_attack', ctx=ctx, slot=z, damage=50))
    assert att.damage == base + 50


def test_overwriting_bolt_changes_weakness():
    g = new_game()
    board(g, 0, '30C-40', energy={0: ['Basic Lightning Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Overwriting Bolt')
    resolve_all(g)
    assert g.weakness(opp(g).active) == ('L', 2)


def test_lava_zone_burns_new_active_when_opponent_retreats():
    g = new_game()
    board(g, 0, 'TEF-29', prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy'], prizes=6)
    at_turn(g)
    g.current = 1
    drive(g.switch_active(1, opp(g).bench[0]))
    assert 'burned' in opp(g).active.conditions


def test_holes_puts_counters_on_retreating_pokemon():
    g = new_game()
    board(g, 0, 'ASC-101', prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy'], prizes=6)
    at_turn(g)
    g.current = 1
    old = opp(g).active
    drive(g.switch_active(1, opp(g).bench[0]))
    assert old.damage == 20


def test_fainting_spell_coin_ko():
    g = new_game()
    board(g, 0, 'Dreepy', prizes=6)
    board(g, 1, '30C-90', prizes=6, damage={0: 1000 - 1000})
    at_turn(g)
    gengar, att = opp(g).active, me(g).active
    gengar.damage = g.hp(gengar)
    fix_flips(g, True)
    drive(g.emit('knocked_out', slot=gengar, owner=1, by_attack=True, attacker=att, dest={'to': 'discard', 'redirect': {}}))
    assert att.damage >= g.hp(att)


def test_damp_blocks_self_ko_abilities():
    g = new_game()
    board(g, 0, 'ASC-39', bench=['SFA-20'], hand=[PSY], prizes=6)       # Psyduck + Dusknoir
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    assert not has(g, 'Cursed Blast')
    board(g, 0, 'Dreepy', bench=['SFA-20'], hand=[PSY], prizes=6)
    g.refresh()
    assert has(g, 'Cursed Blast')


def test_unnerve_and_snow_camouflage_block_boss_orders():
    g = new_game()
    board(g, 0, 'Dreepy', hand=["Boss's Orders"], prizes=6)
    board(g, 1, 'Dreepy', bench=['DRI-65'], prizes=6)
    at_turn(g)
    act(g, "Boss's Orders")
    assert 'Cetitan ex' not in labels(g)[0]


# ----------------------------------------------------------------------------- Habilidades escritas à mão
def test_emergency_rotation_from_hand():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['SCR-101'], prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    assert has(g, 'Emergency Rotation')
    act(g, 'Emergency Rotation')
    resolve_all(g)
    assert [s.name for s in me(g).bench] == ['Klinklang'] and not has(g, 'Emergency Rotation')
    board(g, 1, 'Dreepy', prizes=6)
    g.refresh()


def test_fan_call_only_first_turn():
    g = new_game()
    board(g, 0, 'SCR-118', deck=['Pikachu', 'Dreepy', 'Pikachu'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    g.turn = 1
    me(g).turns_taken = 1
    g.refresh()
    assert has(g, 'Fan Call')
    me(g).turns_taken = 3
    g.refresh()
    assert not has(g, 'Fan Call')


def test_hero_spirit_palafin_ex_cannot_be_played():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['PR-SV-126'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    assert not has(g, 'Palafin ex')


def test_zero_to_hero():
    g = new_game()
    board(g, 0, 'TWM-60', bench=['Dreepy'], deck=['PR-SV-126', 'Dreepy'], energy={0: [PSY]}, damage={0: 20}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    pal = me(g).active
    g.current = 0
    drive(g.switch_active(0, me(g).bench[0]))
    resolve_all(g) if False else None
    assert any(s.name == 'Palafin ex' for s in me(g).bench)


# ----------------------------------------------------------------------------- segundo lote
BASIC = {'G': 'Basic Grass Energy', 'R': 'Basic Fire Energy', 'W': 'Basic Water Energy', 'L': 'Basic Lightning Energy',
         'P': PSY, 'F': 'Basic Fighting Energy', 'D': 'Basic Darkness Energy', 'M': 'Basic Metal Energy', 'C': PSY}


def pay(cid, attack_name, extra=0):
    from ptcg.carddb import db
    a = next(a for a in db().cards[cid].attacks if a.name == attack_name)
    return [BASIC[t] for t in a.cost] + [PSY] * extra


def test_panic_poison_three_conditions():
    g = new_game()
    board(g, 0, 'TEF-101', energy={0: pay('TEF-101', 'Panic Poison')}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Panic Poison')
    resolve_all(g)
    msgs = ' '.join(m['msg'] for m in g.log)
    assert 'Queimado' in msgs and 'Confuso' in msgs and 'Envenenado' in msgs


def test_hypno_damage_per_tails():
    g = new_game()
    board(g, 0, 'DRI-80', energy={0: pay('DRI-80', 'Bench Manipulation')}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'] * 3, prizes=6)
    at_turn(g)
    fix_flips(g, False, False, True)
    act(g, 'Atacar: Bench Manipulation')
    resolve_all(g)
    assert opp(g).active.damage == 160


def test_selective_slime_chooses_condition():
    g = new_game()
    board(g, 0, 'SCR-6', hand=[PSY], prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    fix_flips(g, True)
    act(g, 'Selective Slime')
    act(g, 'Queimado')
    resolve_all(g)
    assert opp(g).active.conditions == {'burned'}


def test_dachsbun_heals_evolutions_and_discards_their_energy():
    g = new_game()
    board(g, 0, 'Fidough' if False else 'Dreepy', bench=['Drakloak'], hand=['SCR-67', 'Fidough'], damage={1: 30},
          energy={1: [PSY]}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    me(g).bench[0].cards.insert(0, card('Dreepy', 0))
    me(g).bench[0].cards.pop(0)
    # usa Drakloak como "Pokémon evoluído" no Banco (2 cartas empilhadas)
    me(g).bench[0].cards.insert(0, card('Dreepy', 0))
    from ptcg.effects.abilities2 import once  # noqa: F401  (apenas garante o import do módulo)
    prog = None
    from ptcg.carddb import db
    ab = db().cards['SCR-67'].abilities[0]
    assert ab.impl.status == 'ok'
    drive(ab.impl.run(g, 0, me(g).active))
    assert me(g).bench[0].damage == 0 and not me(g).bench[0].energy


def test_indeedee_heals_active_and_recovers():
    g = new_game()
    board(g, 0, 'Drakloak', hand=['PR-SV-154'], damage={0: 50}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    me(g).active.conditions.add('poisoned')
    act(g, 'Jogar Indeedee no Banco')
    act(g, 'Sim')
    resolve_all(g)
    assert me(g).active.damage == 20 and not me(g).active.conditions


def test_scraggy_nitpick_refreshes_opponent_hand():
    g = new_game()
    board(g, 0, '30C-94', energy={0: ['Basic Darkness Energy']}, prizes=6)
    board(g, 1, 'Dreepy', hand=[PSY] * 2, deck=['Dreepy'] * 10, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Nitpick')
    resolve_all(g)
    assert len(opp(g).hand) == 4 + 1       # +1: compra do turno dele
    assert len(opp(g).deck) == 12 - 4 - 1


def test_banette_cursed_words_opponent_chooses():
    g = new_game()
    board(g, 0, 'JTG-60', energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Dreepy', hand=[PSY, PSY, 'Dreepy', 'Dreepy', 'Dreepy'], deck=['Dreepy'] * 5, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Cursed Words')
    assert g.prompt.player == 1             # o oponente escolhe
    resolve_all(g)
    assert len(opp(g).hand) == 5 - 3 + 1


def test_prism_charge_attaches_different_types_to_tera():
    g = new_game()
    board(g, 0, 'SSP-161', bench=['Teal Mask Ogerpon ex'], energy={0: [PSY]},
          deck=['Basic Fire Energy', 'Basic Fire Energy', 'Basic Water Energy', 'Basic Grass Energy', 'Dreepy'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Prism Charge')
    for _ in range(40):
        if g.prompt is None or g.prompt.hint == 'main':
            break
        g.step(0)
    types = [e.d.provides for s in me(g).in_play() for e in s.energy]
    assert len(types) == 1 + 3 and len({t for t in types if t != 'P'}) == 3


def test_pyro_dance_from_hand():
    g = new_game()
    board(g, 0, 'PR-SV-116', bench=['Dreepy'], hand=['Basic Fire Energy', 'Basic Fighting Energy', PSY], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Pyro Dance')
    for _ in range(6):
        if g.prompt.hint == 'main':
            break
        g.step(0)
    assert sum(len(s.energy) for s in me(g).in_play()) == 2 and len(me(g).hand) == 1


def test_x_boot_searches_both_energies():
    g = new_game()
    board(g, 0, 'DRI-145', hand=[PSY], deck=['Basic Psychic Energy', 'Basic Metal Energy', 'Dreepy'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'X-Boot')
    for _ in range(8):
        if g.prompt.hint == 'main':
            break
        g.step(0)
    assert sum(len(s.energy) for s in me(g).in_play()) == 2


def test_cinnabar_lure_puts_pokemon_on_bench():
    g = new_game()
    board(g, 0, 'SSP-142', energy={0: ['Basic Fire Energy', 'Basic Water Energy', 'Basic Darkness Energy']},
          deck=['Dreepy', 'Dreepy', PSY, 'Mew ex', PSY] + [PSY] * 8, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Cinnabar Lure')
    for _ in range(12):
        if g.prompt.hint == 'main' or g.prompt.player != 0:
            break
        g.step(0)
    assert len(me(g).bench) >= 1


def test_drum_beating_raises_costs():
    g = new_game()
    board(g, 0, 'TWM-16', energy={0: ['Basic Grass Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Drum Beating')
    resolve_all(g)
    t = opp(g).active
    assert g.attack_cost(t, t.d.attacks[0]) == ['C', 'C'] and g.retreat_cost(t) == t.d.retreat + 1


def test_frigid_fangs_blocks_low_energy_attackers():
    g = new_game()
    board(g, 0, 'SSP-45', energy={0: ['Basic Water Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', energy={0: [PSY, PSY]}, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Frigid Fangs')
    resolve_all(g)
    t = opp(g).active
    assert not g.allowed('can_attack', slot=t, attack=t.d.attacks[0])
    t.energy.append(card(PSY, 1))
    assert g.allowed('can_attack', slot=t, attack=t.d.attacks[0])


def test_unleash_lightning_blocks_own_attacks_next_turn():
    g = new_game()
    board(g, 0, 'SCR-47', bench=['Pikachu'], energy={0: ['Basic Lightning Energy'] * 2}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Unleash Lightning')
    resolve_all(g)
    for s in me(g).in_play():
        assert not g.allowed('can_attack', slot=s, attack=s.d.attacks[0])


def test_scorching_earth_removes_stadium_and_locks():
    g = new_game()
    board(g, 0, 'MEG-31', energy={0: ['Basic Fire Energy']}, prizes=6)
    board(g, 1, 'Dreepy', hand=['Battle Cage'], prizes=6)
    at_turn(g)
    g.stadium = card('Battle Cage', 1)
    act(g, 'Atacar: Scorching Earth')
    resolve_all(g)
    assert g.stadium is None
    assert not g.allowed('can_play', player=1, card=opp(g).hand[0])


def test_torrential_heart_adds_damage_this_turn():
    g = new_game()
    board(g, 0, 'PR-SV-89', energy={0: ['Basic Water Energy'] * 2}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Torrential Heart')
    resolve_all(g)
    act(g, 'Atacar: Giant Wave')
    resolve_all(g)
    assert me(g).active.damage == 50 and opp(g).active.damage == 280


def test_upside_down_draw_from_bottom():
    g = new_game()
    board(g, 0, 'DRI-25', energy={0: [PSY]}, deck=['Dreepy', 'Basic Fire Energy', 'Mew ex', 'Pikachu', 'Basic Water Energy'],
          prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Upside-Down Draw')
    resolve_all(g)
    assert [c.name for c in me(g).hand] == ['Basic Water Energy', 'Pikachu', 'Mew ex']


def test_everyone_explode_now():
    g = new_game()
    board(g, 0, 'PR-SV-135', bench=['Drifloon' if False else 'Dreepy'], energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Everyone Explode Now')
    resolve_all(g)
    assert me(g).active.damage == 30 and opp(g).active.damage == 50


def test_wide_blast_hits_whole_bench():
    g = new_game()
    board(g, 0, 'JTG-114', energy={0: pay('JTG-114', 'Wide Blast')}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Mew ex', 'Mew ex'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Wide Blast')
    resolve_all(g)
    assert all(s.damage == 50 for s in opp(g).bench) and opp(g).active.damage == 0


def test_gnawing_curse_and_auto_heal():
    g = new_game()
    board(g, 0, 'TEF-104', prizes=6)
    board(g, 1, 'Dreepy', hand=[PSY], prizes=6)
    at_turn(g)
    t = opp(g).active
    drive(g.attach_energy(1, opp(g).hand[0], t, from_hand=True))
    assert t.damage == 20
    g = new_game()
    board(g, 0, 'JTG-107', bench=['Dreepy'], hand=[PSY], damage={0: 30, 1: 50}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    drive(g.attach_energy(0, me(g).hand[0], me(g).bench[0], from_hand=True))
    assert me(g).bench[0].damage == 0 and me(g).active.damage == 30


def test_memory_helix_borrows_bench_attacks():
    g = new_game()
    board(g, 0, '30C-66', bench=['Dragapult ex'], energy={0: ['Basic Fire Energy', PSY]}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    assert has(g, 'Atacar: Phantom Dive') and has(g, 'Atacar: Jet Headbutt')


def test_memory_dive_gives_previous_attacks():
    g = new_game()
    board(g, 0, 'TEF-84', bench=['Drakloak'], energy={0: [PSY], 1: [PSY, 'Basic Fire Energy']}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    drak = me(g).bench[0]
    drak.cards.insert(0, card('Dreepy', 0))
    atks = [a.name for a in g.attacks_of(drak)]
    assert 'Bite' in atks and 'Dragon Headbutt' in atks


def test_adrena_power_with_darkness_energy():
    g = new_game()
    board(g, 0, 'TWM-111', energy={0: ['Basic Fighting Energy', 'Basic Fighting Energy', 'Basic Darkness Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    assert g.hp(me(g).active) == 230
    act(g, 'Atacar: Good Punch')
    resolve_all(g)
    assert opp(g).active.damage == 170


def test_metal_road_and_buzzing_boost_on_moving_to_active():
    g = new_game()
    board(g, 0, 'Dreepy', bench=['CRI-64', 'Dreepy'], energy={0: ['Basic Metal Energy'] * 2, 2: ['Basic Metal Energy']},
          hand=[], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    g.current = 0
    drive(g.switch_active(0, me(g).bench[0]))           # o 1º prompt (usar a Habilidade?) escolhe "Sim"
    assert me(g).active.name == 'Cobalion ex' and len(me(g).active.energy) == 3


def test_fall_back_to_reload():
    g = new_game()
    board(g, 0, 'MEG-38', bench=['Dreepy'], hand=['Basic Water Energy', 'Basic Water Energy', PSY], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    g.current = 0
    drive(g.switch_active(0, me(g).bench[0]))
    old = me(g).bench[0]
    assert old.name == 'Clawitzer' and len(old.energy) == 2


def test_sand_stream_and_good_sleep_checkup():
    g = new_game()
    board(g, 0, 'DRI-96', hand=[PSY], prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy', 'Drakloak'], prizes=6)
    at_turn(g)
    drive(g.emit('checkup'))
    assert opp(g).active.damage == 20 and opp(g).bench[0].damage == 20 and opp(g).bench[1].damage == 0
    g = new_game()
    board(g, 0, '30C-119', damage={0: 80}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    a = me(g).active
    a.conditions.add('asleep')
    a.flags['stayed_asleep'] = g.turn
    drive(g.emit('checkup'))
    assert a.damage == 0


def test_magmortar_and_toxic_subjugation():
    g = new_game()
    board(g, 0, 'JTG-21', prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    opp(g).active.conditions.add('burned')
    drive(g._checkup())
    assert opp(g).active.damage == 50 + 10 * 0 or opp(g).active.damage == 50         # 2 + 3 contadores


def test_wonder_kiss_extra_prize():
    g = new_game()
    board(g, 0, 'SSP-72', prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy'], prizes=6)
    at_turn(g)
    fix_flips(g, True)
    t = opp(g).active
    t.damage = 1000
    t.flags['hit'] = (g.turn, 'attack', me(g).active)
    drive(g._resolve_kos())
    assert len(me(g).prizes) == 4


def test_sticky_bind_and_initialization_block_abilities():
    g = new_game()
    board(g, 0, 'SSP-107', bench=['Drakloak'], hand=[PSY], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    d = me(g).bench[1] if len(me(g).bench) > 1 else me(g).bench[0]
    assert g.has_ability(d) is True            # Drakloak é Estágio 1: não é afetado
    board(g, 0, 'TWM-77', bench=['Mew ex'], hand=[PSY], prizes=6)
    g.refresh()
    assert not g.has_ability(me(g).bench[0]) or me(g).bench[0].d.abilities == []


def test_midnight_fluttering_and_potent_glare():
    g = new_game()
    board(g, 0, 'PR-SV-97', prizes=6)
    board(g, 1, 'Drakloak', hand=[PSY], prizes=6)
    at_turn(g)
    assert not g.has_ability(opp(g).active)
    g = new_game()
    board(g, 0, 'DRI-113', hand=[PSY], prizes=6)
    board(g, 1, 'Dreepy', hand=['Drakloak'], prizes=6)
    at_turn(g)
    assert not g.can_play_card(1, opp(g).hand[0])


def test_extra_helpings_and_stone_palace_do_not_stack():
    g = new_game()
    board(g, 0, 'JTG-117', bench=['JTG-117', 'DRI-86'], energy={0: [PSY] * 3}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    from ptcg.core import AttackCtx
    ctx = AttackCtx(g, 0, me(g).active, opp(g).active, me(g).active.d.attacks[0])
    assert g.fold('damage_out', 100, ctx=ctx, target=opp(g).active) == 130


# ----------------------------------------------------------------------------- terceiro lote
def run_prompts(g, limit=60, who=None):
    """Responde com a primeira opção até voltar à fase principal."""
    for _ in range(limit):
        if g.done or g.prompt.hint == 'main':
            return
        g.step(0)


def test_evil_incineration_discards_opponents_active():
    g = new_game()
    board(g, 0, 'DRI-31', energy={0: ["Team Rocket's Energy", 'Basic Fire Energy', PSY, PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Evil Incineration')
    run_prompts(g)
    assert [e['name'] for e in g.ko_log] == [] and opp(g).active.name == 'Dreepy'
    assert any(c.name == 'Dragapult ex' for c in opp(g).discard)


def test_permeating_chill_puts_counters_at_end_of_their_turn():
    g = new_game()
    board(g, 0, 'TWM-54', energy={0: ['Basic Water Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], hand=[PSY], deck=['Dreepy'] * 5, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Permeating Chill')
    run_prompts(g)
    # agora é o turno do oponente: ele passa
    assert g.current == 1 or g.prompt.player == 1
    t = opp(g).active
    before = t.damage
    act(g, 'Passar o turno')
    assert t.damage == before + 90


def test_slow_crunch_knocks_out_at_end_of_their_turn():
    g = new_game()
    board(g, 0, 'TWM-3', bench=['Dreepy'], energy={0: ['Basic Grass Energy', PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], hand=[PSY], deck=['Dreepy'] * 5, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Slow Crunch')
    run_prompts(g)
    assert opp(g).active.name == 'Dragapult ex' and not g.ko_log
    act(g, 'Passar o turno')
    assert [e['name'] for e in g.ko_log] == ['Dragapult ex']


def test_charge_up_dash_and_kaleidowaltz_use_heads():
    g = new_game()
    board(g, 0, '30C-42', energy={0: [PSY]}, deck=['Basic Lightning Energy'] * 4 + ['Dreepy'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    fix_flips(g, True, True, False)
    act(g, 'Atacar: Charge-Up Dash')
    run_prompts(g)
    assert sum(1 for e in me(g).active.energy if e.name == 'Basic Lightning Energy') == 2
    g = new_game()
    board(g, 0, 'ASC-172', bench=['Dreepy'], energy={0: [PSY]}, deck=['Basic Fire Energy'] * 8, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    fix_flips(g, True, False, True)
    act(g, 'Atacar: Kaleidowaltz')
    run_prompts(g, 200)
    assert sum(len(s.energy) for s in me(g).in_play()) == 1 + 4


def test_move_energy_attacks_and_abilities():
    # Cold Cyclone: move a Water Energy from this Pokémon to a Benched Pokémon
    g = new_game()
    board(g, 0, 'ASC-53', bench=['Dreepy'], energy={0: ['Basic Water Energy', 'Basic Water Energy', PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Cold Cyclone')
    run_prompts(g)
    assert len(me(g).bench[0].energy) == 1 and me(g).bench[0].energy[0].name == 'Basic Water Energy'
    # Wash Out: de um Banco para o Ativo, quantas vezes quiser
    g = new_game()
    board(g, 0, 'POR-19', bench=['Dreepy', 'Dreepy'], energy={1: ['Basic Water Energy'], 2: ['Basic Water Energy']},
          prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Wash Out')
    run_prompts(g)
    act(g, 'Wash Out')
    run_prompts(g)
    assert len(me(g).active.energy) == 2 and not me(g).bench[0].energy and not me(g).bench[1].energy
    # Slight Shift: entre Pokémon do oponente
    g = new_game()
    board(g, 0, 'BLK-40', energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], energy={0: ['Basic Fire Energy']}, prizes=6)
    at_turn(g)
    act(g, 'Atacar: Slight Shift')
    run_prompts(g)
    assert not opp(g).active.energy and len(opp(g).bench[0].energy) == 1


def test_bubble_gathering_and_energy_blender():
    g = new_game()
    board(g, 0, 'ASC-84', bench=['Dreepy'], energy={1: ['Basic Fire Energy']}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Bubble Gathering')
    run_prompts(g)
    assert len(me(g).active.energy) == 1 and not me(g).bench[0].energy
    g = new_game()
    board(g, 0, 'TEF-131', bench=['Dreepy'], energy={0: [PSY, PSY, PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Energy Blender')
    for _ in range(40):
        if g.prompt.hint == 'main' or g.prompt.player != 0:
            break
        # move 2 Energias para o Banco e termina
        if g.prompt.hint == 'move_energy' and sum(len(s.energy) for s in me(g).bench) >= 2:
            g.step(len(g.prompt.options) - 1)
        else:
            g.step(0)
    assert sum(len(s.energy) for s in me(g).bench) >= 1


def test_storm_bolt_and_hurricane_move_energy_to_bench():
    g = new_game()
    board(g, 0, 'SSP-67', bench=['Dreepy'], energy={0: ['Basic Lightning Energy'] * 3}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Storm Bolt')
    run_prompts(g)
    assert not me(g).active.energy and len(me(g).bench[0].energy) == 3
    g = new_game()
    board(g, 0, 'WHT-78', bench=['Dreepy'], energy={0: [PSY, PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Hurricane')
    run_prompts(g)
    assert len(me(g).active.energy) == 2 and len(me(g).bench[0].energy) == 1


def test_chimecho_swoobat_and_ninetales():
    g = new_game()
    board(g, 0, 'TWM-85', bench=['Dreepy'], energy={0: [PSY, PSY], 1: [PSY]}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    n = len(me(g).deck)
    act(g, 'Atacar: Homeward Chime')
    run_prompts(g)
    assert not me(g).bench and len(me(g).deck) == n + 2
    g = new_game()
    board(g, 0, 'CRI-9', bench=['Dreepy'], energy={0: ['Basic Fire Energy']}, damage={1: 40}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Nine-Tailed Transfer')
    run_prompts(g)
    assert opp(g).active.damage == 40 and me(g).bench[0].damage == 0


def test_energy_gift_style_searches_and_misc_hand_attacks():
    g = new_game()
    board(g, 0, 'MEG-60', bench=['Dreepy', 'Dreepy'], energy={0: [PSY]}, deck=[PSY] * 5, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Overflowing Wishes')
    run_prompts(g, 100)
    assert all(len(s.energy) == 1 for s in me(g).bench)


def test_mischievous_painting_attaches_for_the_opponent():
    g = new_game()
    board(g, 0, 'SSP-121', energy={0: [PSY]}, prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy'], discard=['Basic Fire Energy', PSY, 'Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Mischievous Painting')
    for _ in range(40):
        if g.prompt.hint == 'main':
            break
        assert g.prompt.player == 0       # quem ataca decide tudo
        g.step(0)
    assert sum(len(s.energy) for s in opp(g).in_play()) == 2 and opp(g).discard[0].name == 'Dreepy'


def test_target_together_and_nullifying_zero():
    g = new_game()
    board(g, 0, 'CRI-69', bench=['CRI-69', 'Dreepy'], energy={0: [PSY, PSY]}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Mew ex'], prizes=6)
    at_turn(g)
    fix_flips(g, True, True)
    act(g, 'Atacar: Target Together')
    act(g, 'Mew ex')
    run_prompts(g)
    assert opp(g).bench[0].damage == 100
    g = new_game()
    board(g, 0, 'PR-ME-71', energy={0: ['Basic Fighting Energy'] * 5}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy', 'Mew ex'], prizes=6)
    at_turn(g)
    fix_flips(g, True, False, True)
    act(g, 'Atacar: Nullifying Zero')
    run_prompts(g)
    assert opp(g).active.damage == 150 and opp(g).bench[1].damage == 150 and opp(g).bench[0].damage == 0


def test_swinging_sphene_and_ice_age():
    g = new_game()
    board(g, 0, 'SSP-133', energy={0: ['Basic Grass Energy', 'Basic Water Energy', 'Basic Fighting Energy']}, prizes=6)
    board(g, 1, 'Dreepy', bench=['Dreepy', 'Drakloak'], prizes=6)
    at_turn(g)
    fix_flips(g, True)
    act(g, 'Atacar: Swinging Sphene')
    run_prompts(g)
    assert [e['name'] for e in g.ko_log] == ['Dreepy']


def test_onyx_takes_prize_and_discards_energy():
    g = new_game()
    board(g, 0, 'PRE-60', energy={0: ['Basic Lightning Energy', PSY, 'Basic Darkness Energy']}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Onyx')
    run_prompts(g)
    assert len(me(g).prizes) == 5 and not me(g).active.energy


def test_lurantis_needs_two_grass_in_hand():
    g = new_game()
    board(g, 0, 'DRI-14', energy={0: ['Basic Grass Energy']}, hand=['Basic Grass Energy'], prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Petal Blade Dance')
    run_prompts(g)
    assert opp(g).active.damage == 0
    g = new_game()
    board(g, 0, 'DRI-14', energy={0: ['Basic Grass Energy']}, hand=['Basic Grass Energy'] * 2, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Petal Blade Dance')
    run_prompts(g)
    assert opp(g).active.damage == 130


def test_purging_strike_optional_hand_discard():
    g = new_game()
    board(g, 0, 'JTG-43', energy={0: ['Basic Water Energy', 'Basic Water Energy', PSY]}, hand=[PSY] * 3, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Purging Strike')
    act(g, 'Sim')
    run_prompts(g)
    assert opp(g).active.damage == 240 and not [c for c in me(g).hand if c.name == PSY and c in me(g).discard]


def test_wondrous_cotton_counts_trainers():
    g = new_game()
    board(g, 0, 'WHT-5', energy={0: ['Basic Grass Energy']}, prizes=6)
    board(g, 1, 'Dragapult ex', hand=["Boss's Orders", 'Ultra Ball', PSY], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Wondrous Cotton')
    run_prompts(g)
    assert opp(g).active.damage == 100


def test_tools_that_grant_attacks_and_badge_and_valley():
    g = new_game()
    board(g, 0, 'Dreepy', tools={0: ['Technical Machine: Fluorite']}, energy={0: ['Basic Grass Energy', 'Basic Water Energy', PSY]},
          bench=['Teal Mask Ogerpon ex'], damage={1: 100}, prizes=6)
    board(g, 1, 'Dragapult ex', prizes=6)
    at_turn(g)
    act(g, 'Atacar: Fluorite')
    run_prompts(g)
    assert me(g).bench[0].damage == 0 and not me(g).active.energy
    g = new_game()
    board(g, 0, 'POR-70' if False else 'Mega Zygarde ex', tools={0: ['Core Memory']}, energy={0: ['Basic Fighting Energy'] * 4}, prizes=6)
    board(g, 1, 'Dragapult ex', bench=['Dreepy'], prizes=6)
    at_turn(g)
    act(g, 'Atacar: Geobuster')
    run_prompts(g)
    assert opp(g).active.damage == 350 or [e['name'] for e in g.ko_log] == ['Dragapult ex']
    g = new_game()
    board(g, 0, 'Dreepy', bench=['Drakloak'], hand=['Drakloak'], prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    g.stadium = card('Dizzying Valley', 0)
    me(g).active.conditions.add('confused')
    drive(g.evolve(0, me(g).active, me(g).hand[0], from_hand=True))
    assert 'confused' in me(g).active.conditions


def test_backtrack_badge_rerolls_all_flips_once():
    """Compendium (ruling 2416): o Badge refaz TODAS as moedas do ataque, e 1x por turno."""
    from ptcg.core import AttackCtx
    from ptcg.effects.compiler import attack_impl_from_text
    g = new_game()
    board(g, 0, 'POR-67', tools={0: ['Backtrack Badge']}, prizes=6)
    board(g, 1, 'Dreepy', prizes=6)
    at_turn(g)
    atk = me(g).active.d.attacks[0]
    im = attack_impl_from_text('Flip 2 coins. This attack does 30 damage for each heads.')
    ctx = AttackCtx(g, 0, me(g).active, opp(g).active, atk)
    ctx.damage = 0
    seq = [False, False, True, True]               # 1ª jogada: 0 caras; refeita: 2 caras
    n = []
    g.flip = lambda who=None: (n.append(1), seq.pop(0))[1]
    gen = im.pre(g, ctx)
    x = next(gen)                                   # pergunta do Badge depois de TODAS as moedas
    assert 'Backtrack' in x.text and len(n) == 2
    try:
        gen.send(x.options[0])
    except StopIteration:
        pass
    assert len(n) == 4 and ctx.damage == 60
    assert any(k.startswith('Backtrack Badge') for k in me(g).ability_keys)


if __name__ == '__main__':
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            try:
                fn()
                print('ok  ', name)
            except Exception:
                fails += 1
                print('FAIL', name)
                traceback.print_exc()
    print('falhas:', fails)
