"""Cenários dos rulings do Compendium (Pokégym) — ver docs/RULINGS_PROGRESSO.md.

    python tests/test_rulings.py      (ou: python -m pytest -q tests/test_rulings.py)
"""
from helpers import act, at_turn, board, has, labels, new_game, resolve_all


def test_r2365_special_red_card_needs_opponent_hand():
    # Ruling: não pode ser jogada se o oponente não tem cartas na mão.
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Special Red Card'], energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy', hand=[], prizes=3)
    at_turn(g)
    assert not has(g, 'Special Red Card'), labels(g)


def test_r2365_special_red_card_playable_with_hand():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Special Red Card'], energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy', hand=['Dreepy'], prizes=3)
    at_turn(g)
    assert has(g, 'Special Red Card'), labels(g)


def test_r2306_vivillon_grand_wing_needs_opponent_hand():
    # Ruling: Grand Wing não pode ser usada se o oponente não tem cartas na mão.
    g = new_game()
    board(g, 0, 'Vivillon', hand=['Basic Psychic Energy'])
    board(g, 1, 'Dreepy', hand=[])
    at_turn(g)
    assert not has(g, 'Grand Wing'), labels(g)


def test_r2418_dark_bell_needs_valid_target():
    # Ruling: sem alvo válido (Pokémon Ativos não Escuros) a carta não pode ser jogada.
    g = new_game()
    board(g, 0, 'Murkrow', hand=['Dark Bell'], energy={0: ['Basic Darkness Energy']})
    board(g, 1, 'Murkrow')            # Escuro: não é alvo válido
    at_turn(g)
    assert not has(g, 'Dark Bell'), labels(g)


def test_r2362_prism_tower_needs_cards_in_deck_and_two_discards():
    g = new_game()
    # Ruling 2362: não pode ser usada com deck vazio.
    board(g, 0, 'Dreepy', hand=['Basic Psychic Energy', 'Basic Fire Energy'], deck=[])
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert not has(g, 'Prism Tower'), labels(g)


def test_r2363_prism_tower_needs_two_discards():
    # Ruling 2363: exige poder descartar 2 cartas.
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Basic Psychic Energy'], deck=['Dreepy'] * 5)
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert not has(g, 'Prism Tower'), labels(g)


def test_r2343_delphox_flaring_magic_needs_room_in_hand():
    # Ruling 2343: não pode usar com 7+ cartas na mão; nenhum descarte acontece.
    g = new_game()
    board(g, 0, 'Delphox', hand=['Basic Fire Energy'] + ['Dreepy'] * 7,
          energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert not has(g, 'Flaring Magic'), labels(g)
    assert len(g.players[0].hand) == 8


def test_r2251_smeargle_can_attach_nothing():
    # Ruling 2251: Energizing Sketch pode escolher não anexar nada.
    g = new_game()
    board(g, 0, 'Smeargle', hand=[], deck=['Basic Psychic Energy'] * 5,
          energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Energizing Sketch')
    resolve_all(g)     # escolhe a opção de não anexar nada (a primeira não é garantida: vê-se abaixo)
    assert len(g.players[0].active.energy) == 1 and not g.done, labels(g)


if __name__ == '__main__':
    import sys
    import traceback

    fails = 0
    fns = [v for k, v in list(globals().items()) if k.startswith('test_') and callable(v)]
    for fn in fns:
        try:
            fn()
            print('ok  ', fn.__name__)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print('FALHA', fn.__name__, '->', str(e)[:300])
            if '-v' in sys.argv:
                traceback.print_exc()
    print(f'falhas: {fails}')
    sys.exit(1 if fails else 0)
