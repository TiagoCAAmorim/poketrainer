"""Cenários dos rulings do Compendium (Pokégym) — ver docs/RULINGS_PROGRESSO.md.

    python tests/test_rulings.py      (ou: python -m pytest -q tests/test_rulings.py)
"""
from helpers import act, at_turn, board, card, has, labels, new_game, resolve_all


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


def test_r2420_lillies_determination_shuffles_and_draws_with_empty_hand():
    # Ruling 2420: a mão é embaralhada no deck mesmo vazia; embaralha antes de comprar (8 com 6 Prêmios).
    g = new_game()
    board(g, 0, 'Dreepy', hand=["Lillie's Determination"], deck=['Dreepy'] * 10)
    board(g, 1, 'Dreepy', deck=['Dreepy'] * 10)
    at_turn(g)
    act(g, "Lillie's Determination")
    resolve_all(g)
    assert len(g.players[0].hand) == 8, labels(g)


def test_r2344_two_garbodors_stack_damage_reduction():
    # Ruling 2344: duas cópias de Gloomy Garbage empilham (−40) contra atacante com Ferramenta.
    g = new_game()
    board(g, 0, 'Dreepy', energy={0: ['Basic Fire Energy', 'Basic Psychic Energy']}, tools={0: ['Air Balloon']})
    board(g, 1, 'Garbodor', bench=['Garbodor'], deck=['Dreepy'] * 5)
    at_turn(g)
    act(g, 'Atacar: Bite')
    resolve_all(g)
    assert g.players[1].active.damage == 0, (g.players[1].active.damage, labels(g))


def test_r2385_ancient_bulwark_only_blocks_attackers_with_two_or_less_energy():
    # Ruling 2385: Bulwark só previne dano de atacantes com 2 ou menos Energias (o regex engolia o ponto final
    # e o filtro nunca casava, bloqueando qualquer atacante).
    def run(n_energy):
        g = new_game()
        board(g, 0, 'PR-ME-81', energy={0: ['Basic Water Energy'] * n_energy})        # Mega Greninja ex
        board(g, 1, 'Dreepy', bench=['PR-ME-85'], prizes=3)                           # Bastiodon no Banco
        at_turn(g)
        act(g, 'Atacar: Ninja Spinner')
        resolve_all(g)
        return g
    assert run(3).prizes_taken(0) == 1, 'com 3 Energias o Bulwark não previne'
    g2 = run(2)
    assert g2.players[1].active is None or g2.players[1].active.damage == 0, 'com 2 Energias o Bulwark bloqueia'


def test_r2399_photon_cord_must_move_at_least_one_energy():
    # Ruling 2399: tem de mover ao menos uma Energia {L} (não oferece "Concluir" com 0 escolhidas).
    g = new_game()
    board(g, 0, 'PR-ME-81', energy={0: ['Basic Water Energy'] * 3})
    board(g, 1, 'PBL-28', bench=['Dreepy'], energy={0: ['Basic Lightning Energy'] * 2}, prizes=3)
    at_turn(g)
    act(g, 'Atacar: Ninja Spinner')
    for _ in range(10):
        if g.prompt.hint == 'pick' and any('Raio' in (g.prompt.text or '') for _ in [0]):
            break
        if g.done or g.prompt.hint == 'main':
            break
        g.step(0)
    assert g.prompt.hint == 'pick', (g.prompt.hint, g.prompt.text)
    assert not any('Concluir' in l for l in labels(g)), labels(g)


def test_r2386_binding_flame_does_not_change_fossil_retreat_cost():
    # Ruling 2386: o custo de Recuo dos Fósseis é fixo (0) e não pode ser alterado.
    g = new_game()
    board(g, 0, 'PBL-115')                                  # Mega Chandelure ex (Binding Flame)
    board(g, 1, 'PBL-72')                                   # Antique Armor Fossil no Ativo
    at_turn(g)
    assert g.retreat_cost(g.players[1].active) == 0
    board(g, 1, 'Dreepy')
    g.refresh()
    assert g.retreat_cost(g.players[1].active) == g.players[1].active.d.retreat + 1   # controle: +1 num Pokémon normal


def test_r2315_nasty_plot_takes_at_least_one_card():
    # Ruling 2315: Nasty Plot deve pegar ao menos 1 carta, se possível.
    g = new_game()
    board(g, 0, 'POR-16', energy={0: ['Basic Fire Energy']}, deck=['Dreepy', 'Basic Psychic Energy', 'Pikachu'])
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Atacar: Nasty Plot')
    assert not any('Concluir' in l for l in labels(g)), labels(g)     # a 1ª carta é obrigatória
    resolve_all(g)
    assert len(g.players[0].hand) == 2


def test_r2317_sand_attack_before_confusion():
    # Ruling 2317: a moeda do Sand Attack vem antes da Confusão; com coroa o ataque não acontece e não há
    # moeda de Confusão nem autodano.
    g = new_game()
    board(g, 0, 'POR-39', energy={0: ['Basic Fighting Energy']})
    board(g, 1, 'Dreepy', energy={0: ['Basic Psychic Energy']}, deck=['Dreepy'] * 5)
    at_turn(g)
    act(g, 'Atacar: Sand Attack')
    resolve_all(g)
    assert g.current == 1 and g.prompt.hint == 'main', (g.current, g.prompt.hint)
    att = g.players[1].active
    base = att.damage
    att.conditions.add('confused')
    g.flip = lambda who=None: False              # tudo coroa
    g.refresh()
    act(g, 'Atacar: Petty Grudge')
    resolve_all(g)
    assert att.damage == base, (att.damage, base)
    assert 'Confuso e se feriu' not in ' '.join(m['msg'] for m in g.log[-5:]), g.log[-5:]


def test_r2405_lively_cutter_after_heal():
    # Ruling 2405: "foi curado neste turno" — a cura grava o turno no Pokémon.
    g = new_game()
    board(g, 0, 'PBL-4', energy={0: ['Basic Grass Energy']}, damage={0: 50})
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert g.heal(g.players[0].active, 30) == 30
    assert g.players[0].active.flags.get('healed_turn') == g.turn


def test_r2423_bellowing_thunder_damages_before_discarding_energy():
    # Ruling 2423: o dano acontece antes do descarte de Energia; o Ancient Bulwark (atacante com 2 ou menos
    # Energias) não bloqueia um atacante que tinha 3 no momento do dano.
    g = new_game()
    board(g, 0, 'PR-SV-145', energy={0: ['Basic Lightning Energy', 'Basic Fighting Energy', 'Basic Lightning Energy']})
    board(g, 1, 'Dreepy', bench=['PR-ME-85'], prizes=3)
    at_turn(g)
    act(g, 'Atacar: Bellowing Thunder')
    resolve_all(g)                     # descarta as 3 Energias
    assert g.prizes_taken(0) == 1, labels(g)
    assert not g.players[0].active.energy


def test_r2370_mentally_calm_keeps_energy_but_bonus_still_applies():
    # Ruling 2370: a Energia de Água permanece anexada (Mentally Calm), mas o dano extra do Ninja Spinner vale.
    g = new_game()
    board(g, 0, 'PR-ME-81', energy={0: ['Basic Water Energy'] * 3})
    board(g, 1, 'Dreepy', bench=['TWM-50'], prizes=3)
    at_turn(g)
    act(g, 'Atacar: Ninja Spinner')
    resolve_all(g)
    assert len(g.players[0].active.energy) == 3, g.players[0].active.energy
    assert g.prizes_taken(0) == 1


def test_r2408_mist_energy_blocks_shellnado_spin_counters():
    # Ruling 2408: os contadores atrasados do Shellnado Spin são efeito de ataque; Mist Energy os bloqueia
    # (o dano do ataque em si, 180, continua valendo).
    g = new_game()
    board(g, 0, 'PBL-31', energy={0: ['Basic Psychic Energy'] * 3})
    board(g, 1, 'PBL-45', energy={0: ['Basic Fighting Energy'] * 2 + ['Mist Energy']}, prizes=3)
    at_turn(g)
    act(g, 'Atacar: Shellnado Spin')
    resolve_all(g)
    assert g.current == 1 and g.prompt.hint == 'main', (g.current, g.prompt.hint)
    act(g, 'Atacar: Rowdy Hammer')
    resolve_all(g)
    assert g.players[1].active.damage == 180, g.players[1].active.damage


def test_r2408_control_without_mist_energy_takes_counters():
    g = new_game()
    board(g, 0, 'PBL-31', energy={0: ['Basic Psychic Energy'] * 3})
    board(g, 1, 'PBL-45', energy={0: ['Basic Fighting Energy'] * 2}, prizes=3)
    at_turn(g)
    act(g, 'Atacar: Shellnado Spin')
    resolve_all(g)
    act(g, 'Atacar: Rowdy Hammer')
    resolve_all(g)
    assert g.players[1].active.damage == 300, g.players[1].active.damage     # 180 + 12 contadores


def test_r2312_wash_out_moves_legacy_energy():
    # Ruling 2312: Energia Especial que fornece {W} (Legacy Energy) pode ser movida pelo Wash Out.
    g = new_game()
    board(g, 0, 'POR-19', bench=['Dreepy'], energy={1: ['Legacy Energy']})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Wash Out')
    resolve_all(g)
    assert [e.name for e in g.players[0].active.energy] == ['Legacy Energy'], labels(g)


def test_r2403_fruity_aroma_does_not_shuffle_when_nothing_returns():
    # Ruling 2403: sem carta voltando ao baralho, não embaralha.
    def run(deck):
        g = new_game()
        board(g, 0, 'PBL-1', energy={0: ['Basic Grass Energy']}, deck=deck)
        board(g, 1, 'Dreepy')
        at_turn(g)
        n = []
        real = g.shuffle
        g.shuffle = lambda p, *a, **k: (n.append(p), real(p, *a, **k))[1]
        act(g, 'Atacar: Fruity Aroma')
        resolve_all(g)
        return len(n), len(g.players[0].hand)
    assert run(['Dreepy'] * 6 + ['Basic Psychic Energy'] * 3) == (0, 6)
    assert run(['Dreepy'] * 3 + ['Basic Psychic Energy'] * 3 + ['Dreepy']) == (1, 3)


def test_r2424_spiky_hopper_ignores_ancient_bulwark_on_the_bench():
    # Ruling 2424: o Bulwark vale para todos os Pokémon do jogador, mas Spiky Hopper ignora efeitos no Ativo.
    g = new_game()
    board(g, 0, 'PFL-84', energy={0: ['Basic Psychic Energy'] * 2})
    board(g, 1, 'Dreepy', bench=['PR-ME-85'], prizes=3)
    at_turn(g)
    act(g, 'Atacar: Spiky Hopper')
    resolve_all(g)
    assert g.prizes_taken(0) == 1, labels(g)       # 160 contra o Dreepy: nocauteado apesar do Bastiodon


def test_r2393_destructive_headbutting_needs_energy_and_hide_n_sneak_blocks_it():
    # Ruling 2393: sem Energia no Ativo do oponente a Habilidade não pode ser usada; Hide 'n' Sneak
    # (efeito de Habilidade) bloqueia o descarte.
    g = new_game()
    board(g, 0, 'PBL-45')
    board(g, 1, 'PBL-34')                                           # Banette sem Energia
    at_turn(g)
    assert not has(g, 'Destructive Headbutting'), labels(g)
    g = new_game()
    board(g, 0, 'PBL-45')
    board(g, 1, 'PBL-34', energy={0: ['Basic Psychic Energy']})
    at_turn(g)
    g.flip = lambda who=None: True
    act(g, 'Destructive Headbutting')
    resolve_all(g)
    assert len(g.players[1].active.energy) == 1, 'Hide n Sneak impede o descarte'
    g = new_game()
    board(g, 0, 'PBL-45')
    board(g, 1, 'Dreepy', energy={0: ['Basic Psychic Energy']})        # controle
    at_turn(g)
    g.flip = lambda who=None: True
    act(g, 'Destructive Headbutting')
    resolve_all(g)
    assert len(g.players[1].active.energy) == 0


def test_r2345_gloomy_garbage_also_reduces_bench_damage():
    # Ruling 2345: a redução de 20 vale também para o dano do ataque ao Banco (Keldeo, Shoot Through).
    def run(garbodor):
        g = new_game()
        board(g, 0, 'CRI-19', energy={0: ['Basic Water Energy']}, tools={0: ['Air Balloon']})
        board(g, 1, 'Garbodor' if garbodor else 'Dreepy', bench=['Dreepy'])
        at_turn(g)
        act(g, 'Atacar: Shoot Through')
        resolve_all(g)
        return g.players[1].bench[0].damage
    assert run(False) == 20
    assert run(True) == 0


def test_r2353_pleasing_present_attachment_is_simultaneous():
    # Ruling 2353: o oponente escolhe primeiro, mas nenhuma Energia é ligada antes de todas as escolhas.
    g = new_game()
    board(g, 0, 'CRI-18', energy={0: ['Basic Psychic Energy']}, hand=['Basic Fire Energy'])
    board(g, 1, 'Dreepy', hand=['Basic Water Energy'])
    at_turn(g)
    act(g, 'Atacar: Pleasing Present')
    seen = {}
    for _ in range(12):
        if g.done or g.prompt.hint == 'main':
            break
        if g.prompt.player == 0 and g.prompt.hint in ('attach_from_hand', 'attach_target'):
            seen.setdefault('opp_energy_when_p0_chooses', len(g.players[1].active.energy))
        g.step(0)
    assert seen.get('opp_energy_when_p0_chooses') == 0, seen       # ainda nada ligado no Pokémon do oponente
    assert len(g.players[1].active.energy) == 1 and len(g.players[0].active.energy) == 2


def test_r2340_erasure_ball_adds_damage_per_discarded_card():
    # Ruling 2340: 160 de base, +60 por Energia descartada do Banco, no máximo 2 (160 / 220 / 280).
    # (O Mewtwo ex só ataca com 4+ Pokémon Team Rocket em jogo.)
    def run(bench_energy, picks):
        g = new_game()
        board(g, 0, 'DRI-81', bench=['DRI-81'] * 3,
              energy={0: ['Basic Psychic Energy'] * 3, 1: ['Basic Psychic Energy'] * bench_energy})
        board(g, 1, 'PBL-45', prizes=3)
        at_turn(g)
        act(g, 'Atacar: Erasure Ball')
        for i in range(picks):                         # descarta `picks` cartas e então "Concluir"
            if g.prompt.hint != 'discard_energy_any':
                break
            g.step(0)
        while not g.done and g.prompt.hint != 'main':
            g.step(len(g.prompt.options) - 1 if g.prompt.hint == 'discard_energy_any' else 0)
        return g.players[1].active.damage
    assert run(0, 0) == 160
    assert run(3, 0) == 160                            # escolhe não descartar
    assert run(3, 1) == 220
    assert run(3, 2) == 280                            # o limite é 2, mesmo com 3 Energias no Banco


def test_r2311_memory_dive_and_sniper_eye():
    # Ruling 2311: sem Memory Dive só valem os ataques da carta do topo; com o Relicanth no Banco, o Decidueye ex
    # usa os da evolução anterior (Dartrix), e Sniper's Eye (oponente com exatamente 4 cartas) ignora os {C}.
    def run(relicanth, energy, opp_hand):
        g = new_game()
        board(g, 0, 'POR-12', bench=['TEF-84'] if relicanth else ['Dreepy'], energy={0: energy})
        s = g.players[0].active
        s.cards = [card('POR-11', 0), s.cards[-1]]                    # Dartrix embaixo do Decidueye ex
        board(g, 1, 'Dreepy', bench=['Dreepy'], hand=['Dreepy'] * opp_hand)
        at_turn(g)
        return g
    assert not has(run(False, ['Basic Grass Energy'] * 3, 4), 'Feather Shot')
    assert has(run(True, ['Basic Grass Energy'] * 3, 4), 'Feather Shot')
    assert has(run(True, [], 4), 'Feather Shot')            # {C}{C}{C} ignorados com 4 cartas na mão do oponente
    assert not has(run(True, [], 3), 'Feather Shot')


def test_r2400_push_down_sends_active_to_bench_with_attachments():
    # Ruling 2400: o oponente escolhe o novo Ativo (nunca o Pokémon enviado), e o Pokémon enviado vai ao Banco
    # com tudo que estiver ligado a ele; sem Banco, só o dano acontece.
    g = new_game()
    board(g, 0, 'PBL-44', energy={0: ['Basic Fighting Energy'] * 2})                  # Cranidos
    board(g, 1, 'PBL-45', bench=['Dreepy', 'Pikachu'], energy={0: ['Basic Lightning Energy'] * 2},
          tools={0: ['Air Balloon']}, damage={0: 20})
    at_turn(g)
    act(g, 'Atacar: Push Down')
    assert g.prompt.player == 1 and g.prompt.hint == 'promote', (g.prompt.player, g.prompt.hint)
    assert not any('Rampardos' in l for l in labels(g)), labels(g)
    act(g, 'Pikachu')
    resolve_all(g)
    p1 = g.players[1]
    assert p1.active.name == 'Pikachu'
    sent = next(x for x in p1.bench if x.name == 'Rampardos ex')
    assert (len(sent.energy), len(sent.tools), sent.damage) == (2, 1, 90)
    g = new_game()
    board(g, 0, 'PBL-44', energy={0: ['Basic Fighting Energy'] * 2})
    board(g, 1, 'PBL-45')
    at_turn(g)
    act(g, 'Atacar: Push Down')
    resolve_all(g)
    assert g.players[1].active.name == 'Rampardos ex' and g.players[1].active.damage == 70


def test_r2354_pleasing_present_energy_on_unaware_skeledirge_is_discarded():
    # Ruling 2354: o oponente pode escolher o Skeledirge (Unaware), mas a Energia é descartada depois da escolha.
    g = new_game()
    board(g, 0, 'CRI-18', energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'SSP-31', hand=['Basic Water Energy'])
    at_turn(g)
    act(g, 'Atacar: Pleasing Present')
    resolve_all(g)
    assert not g.players[1].active.energy, g.players[1].active.energy
    assert any(c.name == 'Basic Water Energy' for c in g.players[1].discard)


def test_r2325_oceanic_curse_blocks_items_and_tools_from_hand():
    # Ruling 2325: Jellicent ex no Ativo -> o oponente não joga Itens nem Ferramentas da mão.
    def run(active):
        g = new_game()
        board(g, 0, active)
        board(g, 1, 'Dreepy', hand=['Ultra Ball', 'Air Balloon', 'Basic Psychic Energy'])
        g.turn = 6
        g.current = 1
        for pl in g.players:
            pl.turns_taken = 3
        g.refresh()
        return g
    g = run('WHT-45')
    assert not has(g, 'Ultra Ball') and not has(g, 'Air Balloon'), labels(g)
    g = run('Dreepy')
    assert has(g, 'Ultra Ball') and has(g, 'Air Balloon'), labels(g)


def test_r2305_stadium_change_completes_before_gravity_mountain_hp_loss():
    # Ruling 2305: a troca de Estádio se completa primeiro (Área Zero: descarte do Banco até 5), só então vale o -30 HP.
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Gravity Mountain'])
    board(g, 1, 'Dreepy', bench=['Dreepy'] * 7)
    g.stadium = card('Area Zero Underdepths', 1)
    at_turn(g)
    act(g, 'Gravity Mountain')
    resolve_all(g)
    assert g.stadium is not None and g.stadium.name == 'Gravity Mountain'
    assert len(g.players[1].bench) == 5, len(g.players[1].bench)


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
