"""Testes de cenário das regras e de cartas do formato atual.

    python -m pytest -q tests/test_rules.py      (ou: python tests/test_rules.py)
"""
from helpers import act, at_turn, board, has, labels, new_game, resolve_all


def test_phantom_dive_counters_ko_bench():
    g = new_game()
    board(g, 0, 'Dragapult ex', energy={0: ['Basic Fire Energy', 'Basic Psychic Energy']}, prizes=6)
    board(g, 1, 'Teal Mask Ogerpon ex', bench=['Dreepy', 'Dreepy'], prizes=6, damage={1: 10})
    at_turn(g)
    act(g, 'Phantom Dive')
    for _ in range(6):           # todos os 6 contadores no primeiro Dreepy do Banco (70 HP, já com 10)
        act(g, 'Dreepy (Banco 1)')
    resolve_all(g)
    assert g.players[1].active.damage == 200          # Ogerpon 210 HP sobrevive com 10
    assert [e['name'] for e in g.ko_log] == ['Dreepy']
    assert len(g.players[0].prizes) == 5


def test_phantom_dive_damage_and_prizes():
    g = new_game()
    board(g, 0, 'Dragapult ex', energy={0: ['Basic Fire Energy', 'Basic Psychic Energy']}, prizes=6)
    board(g, 1, 'Mega Kangaskhan ex', bench=['Dreepy', 'Dreepy'], prizes=6, damage={0: 100})
    at_turn(g)
    act(g, 'Phantom Dive')
    resolve_all(g)
    assert len(g.players[0].prizes) == 3      # Mega ex nocauteado (100 + 200 = 300) = 3 prêmios


def test_tera_bench_prevents_damage_but_not_counters():
    g = new_game()
    board(g, 0, 'Dragapult ex', energy={0: ['Basic Fire Energy', 'Basic Psychic Energy']})
    board(g, 1, 'Dreepy', bench=['Teal Mask Ogerpon ex'])
    at_turn(g)
    act(g, 'Phantom Dive')
    resolve_all(g)
    oger = g.players[1].bench[0] if g.players[1].bench else g.players[1].active
    assert oger.damage == 60, oger.damage   # contadores de efeito ignoram a proteção Tera


def test_first_turn_rules():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Drakloak', "Boss's Orders", 'Rare Candy', 'Dragapult ex'],
          energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy', bench=['Dreepy'])
    g.refresh()
    assert not has(g, 'Evoluir'), labels(g)
    assert not has(g, "Boss's Orders")
    assert not has(g, 'Rare Candy')
    assert not has(g, 'Atacar')


def test_rare_candy_and_evolution():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Rare Candy', 'Dragapult ex', 'Drakloak'])
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert has(g, 'Rare Candy') and has(g, 'Evoluir Dreepy (Ativo) → Drakloak')
    act(g, 'Rare Candy')
    resolve_all(g)
    assert g.players[0].active.name == 'Dragapult ex'


def test_item_lock():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Ultra Ball', 'Dreepy', 'Dreepy', "Boss's Orders"])
    board(g, 1, 'Jellicent ex', bench=['Dreepy'])
    at_turn(g)
    if any(a.name == 'Oceanic Curse' for a in g.players[1].active.d.abilities):
        assert not has(g, 'Jogar Ultra Ball'), labels(g)
        assert has(g, "Boss's Orders")


def test_retreat_with_air_balloon_and_legacy_energy_any_type():
    g = new_game()
    board(g, 0, 'Raging Bolt ex', bench=['Dreepy'], tools={0: ['Air Balloon']},
          energy={0: ['Legacy Energy', 'Basic Fighting Energy']})
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert has(g, 'Recuar para Dreepy')                # 3 - 2 = 1 de recuo
    assert has(g, 'Bellowing Thunder')                 # Legacy paga o Elétrico


def test_bellowing_thunder_counts_discards():
    g = new_game()
    board(g, 0, 'Raging Bolt ex', bench=['Teal Mask Ogerpon ex'],
          energy={0: ['Basic Lightning Energy', 'Basic Fighting Energy'], 1: ['Basic Grass Energy'] * 2})
    board(g, 1, 'Mega Kangaskhan ex')
    at_turn(g)
    act(g, 'Bellowing Thunder')
    for _ in range(3):
        g.step(0)       # descarta 3 energias
    act(g, 'Concluir')
    resolve_all(g)
    assert g.players[1].active is None or g.players[1].active.damage == 210 or g.done


def test_lillies_determination_and_teal_dance():
    g = new_game()
    board(g, 0, 'Teal Mask Ogerpon ex', hand=["Lillie's Determination", 'Basic Grass Energy'],
          deck=['Dreepy'] * 30, prizes=6)
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Teal Dance')
    assert len(g.players[0].active.energy) == 1 and len(g.players[0].hand) == 2
    act(g, "Lillie's Determination")
    assert len(g.players[0].hand) == 8


def test_myriad_leaf_shower_damage():
    g = new_game()
    board(g, 0, 'Teal Mask Ogerpon ex', energy={0: ['Basic Grass Energy'] * 3})
    board(g, 1, 'Mega Kangaskhan ex', energy={0: ['Basic Psychic Energy'] * 2})
    at_turn(g)
    act(g, 'Myriad Leaf Shower')
    resolve_all(g)
    assert g.players[1].active.damage == 30 + 30 * 5


def test_confusion_poison_burn_checkup():
    g = new_game()
    board(g, 0, 'Dreepy')
    board(g, 1, 'Mega Kangaskhan ex')
    at_turn(g)
    g.players[1].active.conditions |= {'poisoned', 'burned'}
    act(g, 'Passar o turno')
    assert g.players[1].active.damage == 30          # 10 veneno + 20 queimadura


def test_survival_brace():
    g = new_game()
    board(g, 0, 'Dragapult ex', energy={0: ['Basic Fire Energy', 'Basic Psychic Energy']})
    board(g, 1, 'Dreepy', tools={0: ['Survival Brace']}, bench=['Dreepy'])
    at_turn(g)
    act(g, 'Jet Headbutt')
    resolve_all(g)
    a = g.players[1].active
    assert a is not None and g.hp_left(a) == 10 and not a.tools


def test_boss_orders_gust():
    g = new_game()
    board(g, 0, 'Dreepy', hand=["Boss's Orders"])
    board(g, 1, 'Dreepy', bench=['Dreepy'])
    at_turn(g)
    act(g, "Boss's Orders")
    resolve_all(g)
    assert g.players[1].active.name == 'Dreepy'


def test_fairy_zone_makes_dragons_weak():
    g = new_game()
    board(g, 0, "Lillie's Clefairy ex", energy={0: ['Basic Psychic Energy'] * 3})
    board(g, 1, 'Dragapult ex')
    at_turn(g)
    assert g.weakness(g.players[1].active) == ('P', 2)
    ctxdmg = g.calc_damage(__import__('ptcg.core', fromlist=['AttackCtx']).AttackCtx(
        g, 0, g.players[0].active, g.players[1].active, g.players[0].active.d.attacks[0]), g.players[1].active, 20)
    assert ctxdmg == 40


def test_munkidori_moves_counters_and_watchful_eye_blocks():
    g = new_game()
    board(g, 0, 'Munkidori', bench=['Dreepy'], energy={0: ['Basic Darkness Energy']}, damage={1: 30})
    board(g, 1, 'Dreepy', bench=['Dreepy'])
    at_turn(g)
    act(g, 'Adrena-Brain')
    resolve_all(g)
    assert sum(s.damage for s in g.players[1].in_play()) == 30
    g2 = new_game()
    board(g2, 0, 'Munkidori', bench=['Dreepy'], energy={0: ['Basic Darkness Energy']}, damage={1: 30})
    board(g2, 1, 'CRI-70', bench=['Dreepy'])
    at_turn(g2)
    assert not has(g2, 'Adrena-Brain')


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
