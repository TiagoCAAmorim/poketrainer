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


def test_r2131_area_zero_bench_trimmed_before_promotion():
    # Ruling 2131: ao perder o Ativo Tera, o Banco é reduzido a 5 antes de promover o novo Ativo.
    g = new_game()
    board(g, 0, 'Dreepy', energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Miraidon ex', bench=['Dreepy'] * 8, damage={0: 210})
    g.stadium = card('Area Zero Underdepths', 1)
    at_turn(g)
    act(g, 'Petty Grudge')
    hints = []
    for _ in range(20):
        if g.prompt.hint == 'main' or g.winner is not None:
            break
        hints.append(g.prompt.hint)
        g.step(0)
    assert hints.index('discard_bench') < hints.index('promote'), hints
    assert len(g.players[1].bench) <= 5, len(g.players[1].bench)


def test_r2213_pyroar_intimidating_fang_reduces_bench_damage():
    # Ruling 2213: a redução de Intimidating Fang vale também para o dano ao Banco.
    g = new_game()
    board(g, 0, 'Ferrothorn', energy={0: ['Basic Metal Energy'] * 3}, bench=['Dreepy'])
    board(g, 1, 'Pyroar', bench=['Dreepy'])
    at_turn(g)
    act(g, 'Kaboom Needles')
    assert g.players[1].active.damage == 20, g.players[1].active.damage
    assert g.players[1].bench[0].damage == 20, g.players[1].bench[0].damage


def test_r2161_oil_salvo_sums_hits_before_granite_cave():
    # Ruling 2161: 6 escolhas do mesmo alvo = 120 somados; Granite Cave (-30) aplica uma vez só: 90.
    g = new_game()
    board(g, 0, 'Arboliva ex', energy={0: ['Basic Grass Energy'] * 3})
    board(g, 1, "Steven's Metagross ex")
    g.stadium = card('Granite Cave', 1)
    at_turn(g)
    act(g, 'Oil Salvo')
    for _ in range(10):
        if g.prompt.hint == 'main':
            break
        g.step(0)
    assert g.players[1].active.damage == 90, g.players[1].active.damage

def test_r2258_grimsleys_move_any_stage_darkness():
    # Ruling 2258: qualquer Pokémon {D} (não só Básico) pode ir direto ao Banco.
    g = new_game()
    board(g, 0, 'Dreepy', hand=["Grimsley's Move"], deck=['Dreepy', 'Zoroark'] + ['Basic Psychic Energy'] * 8)
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, "Grimsley's Move")
    resolve_all(g)
    assert any(s.name == 'Zoroark' for s in g.players[0].bench), [s.name for s in g.players[0].bench]


def test_r2257_munkidori_battle_cage_counters_vanish():
    # Ruling 2257: com Battle Cage a colocação é impedida, mas os contadores saem do Munkidori.
    g = new_game()
    board(g, 0, 'Munkidori', energy={0: ['Basic Darkness Energy']}, damage={0: 30})
    board(g, 1, 'Dreepy', bench=['Dreepy'])
    g.stadium = card('Battle Cage', 1)
    at_turn(g)
    act(g, 'Adrena-Brain')
    for _ in range(6):
        if g.prompt.hint == 'main':
            break
        g.step(len(g.prompt.options) - 1 if g.prompt.hint == 'counters' else 0)   # alvo: o Pokémon do Banco
    assert g.players[0].active.damage == 0, g.players[0].active.damage
    assert all(s.damage == 0 for s in g.players[1].in_play())


def test_r2249_suicune_crystal_fall_counts_water_energy():
    # Ruling 2249: 4+ Energias {W} em jogo (Prism Energy conta em Básico) = +90.
    for en in (['Basic Water Energy'] * 4, ['Basic Water Energy'] * 3 + ['Prism Energy']):
        g = new_game()
        board(g, 0, 'PFL-26', energy={0: en})
        board(g, 1, 'Dragapult ex')
        at_turn(g)
        act(g, 'Crystal Fall')
        assert g.players[1].active.damage in (120, 240), g.players[1].active.damage
    g = new_game()
    board(g, 0, 'PFL-26', energy={0: ['Basic Water Energy'] * 3})
    board(g, 1, 'Dragapult ex')
    at_turn(g)
    act(g, 'Crystal Fall')
    assert g.players[1].active.damage == 30, g.players[1].active.damage


def test_r2292_roto_call_only_rotom():
    # Ruling 2292: só Pokémon com "Rotom" no nome.
    g = new_game()
    board(g, 0, 'ASC-92', energy={0: ['Basic Lightning Energy']}, deck=['Fan Rotom', 'Rotom ex', 'Dreepy', 'Rotom'])
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Roto Call')
    assert 'Dreepy' not in labels(g), labels(g)
    resolve_all(g)
    assert all('Rotom' in s.name for s in g.players[0].bench), [s.name for s in g.players[0].bench]


def test_r2265_gale_thrust_after_retreat_only():
    # Ruling 2265: +170 se este Pokémon foi movido do Banco ao Ativo neste turno.
    g = new_game()
    board(g, 0, 'Dreepy', bench=['PFL-84'], energy={0: ['Basic Psychic Energy'], 1: ['Basic Water Energy']})
    board(g, 1, 'PR-ME-30')
    at_turn(g)
    act(g, 'Recuar')
    resolve_all(g)
    act(g, 'Gale Thrust')
    assert g.players[1].active.damage == 230, g.players[1].active.damage


def test_r2167_bother_bot_playability():
    # Ruling 2167: jogável se há prêmio virado para baixo ou carta na mão do oponente.
    BB = "Team Rocket's Bother-Bot"
    g = new_game()
    board(g, 0, 'Dreepy', hand=[BB, 'Dreepy'], deck=['Dreepy'] * 5)
    board(g, 1, 'Dreepy', hand=[], prizes=2)
    for x in g.players[1].prizes:
        x.face_up = True
    at_turn(g)
    assert not has(g, 'Bother-Bot'), labels(g)
    g = new_game()
    board(g, 0, 'Dreepy', hand=[BB, 'Dreepy'], deck=['Dreepy'] * 5)
    board(g, 1, 'Dreepy', hand=[], prizes=3)
    at_turn(g)
    act(g, 'Bother-Bot')
    resolve_all(g)
    assert sum(1 for x in g.players[1].prizes if x.face_up) == 1


def test_r2241_excited_heal_with_basic_mega_ex():
    # Ruling 2241: Mega Heracross ex (Básico) conta como "Grass Mega Evolution Pokémon ex".
    g = new_game()
    board(g, 0, 'PFL-4', bench=['PFL-7'], energy={0: ['Basic Psychic Energy']}, damage={1: 50})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Excited Heal')
    resolve_all(g)
    assert g.players[0].bench[0].damage == 0, g.players[0].bench[0].damage


def test_r2231_r2232_mystery_garden_needs_draw():
    g = new_game()
    board(g, 0, 'Dreepy', bench=['Dreepy', 'Dreepy'], hand=['Basic Psychic Energy'], deck=[])
    board(g, 1, 'Dreepy')
    g.stadium = card('Mystery Garden', 0)
    at_turn(g)
    assert not has(g, 'Mystery Garden'), labels(g)   # deck vazio
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Basic Psychic Energy', 'Dreepy', 'Dreepy'], deck=['Dreepy'] * 5)
    board(g, 1, 'Dreepy')
    g.stadium = card('Mystery Garden', 0)
    at_turn(g)
    assert not has(g, 'Mystery Garden'), labels(g)   # não compraria nada
    board(g, 0, 'Munkidori', bench=['Munkidori', 'Munkidori'], hand=['Basic Psychic Energy'], deck=['Dreepy'] * 5)
    g.refresh()
    assert has(g, 'Mystery Garden'), labels(g)


def test_r2109_inviting_wink_needs_opponent_bench_space():
    # Ruling 2109: com o Banco do oponente cheio, Inviting Wink não pode ser usada.
    g = new_game()
    board(g, 0, "Lillie's Cutiefly", hand=["Lillie's Ribombee"], energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy', bench=['Dreepy'] * 5, hand=['Dreepy', 'Dreepy'])
    at_turn(g)
    act(g, 'Ribombee')
    assert g.prompt.hint != 'yes_no' and 'Inviting Wink' not in g.prompt.text, (g.prompt.hint, g.prompt.text)
    g = new_game()
    board(g, 0, "Lillie's Cutiefly", hand=["Lillie's Ribombee"], energy={0: ['Basic Psychic Energy']})
    board(g, 1, 'Dreepy', bench=['Dreepy'] * 4, hand=['Dreepy', 'Dreepy'])
    at_turn(g)
    act(g, 'Ribombee')
    assert 'Inviting Wink' in g.prompt.text, g.prompt.text


def test_r2375_mist_energy_cannot_be_moved_by_slight_shift():
    # Ruling 2375: Mist Energy no Pokémon Defensor não pode ser movida pelo Slight Shift.
    g = new_game()
    board(g, 0, 'Elgyem', energy={0: ['Basic Psychic Energy'] * 2})
    board(g, 1, 'Dreepy', bench=['Dreepy'], energy={0: ['Mist Energy']})
    at_turn(g)
    act(g, 'Slight Shift')
    resolve_all(g)
    assert [e.name for e in g.players[1].active.energy] == ['Mist Energy'], g.players[1].active.energy



def test_r2199_odor_sleuth_takes_up_to_heads_at_least_one():
    # Ruling 2199: pega até o número de caras (3), e ao menos uma se possível.
    g = new_game()
    board(g, 0, 'WHT-76', energy={0: ['Basic Psychic Energy'] * 2}, discard=['Dreepy', 'Basic Psychic Energy', 'Drakloak'])
    board(g, 1, 'Dreepy')
    g.flip = lambda who=None: True
    at_turn(g)
    act(g, 'Odor Sleuth')
    assert 'Concluir' not in labels(g), labels(g)       # mínimo = min(caras, descarte) = 3
    for _ in range(4):
        if g.prompt.hint == 'main':
            break
        g.step(0)
    assert len(g.players[0].hand) == 3, len(g.players[0].hand)


def test_r2194_firefighting_discards_prism_energy_from_basic():
    # Ruling 2194: Prism Energy num Básico conta como {R} e pode ser descartada.
    g = new_game()
    board(g, 0, 'WHT-25', energy={0: ['Basic Water Energy'] * 2})
    board(g, 1, 'Dreepy', energy={0: ['Prism Energy']})
    at_turn(g)
    act(g, 'Firefighting')
    resolve_all(g)
    assert not g.players[1].active.energy, g.players[1].active.energy


def test_r2212_cinderace_counts_as_basic_in_setup():
    # Ruling 2212 (+ usuário): na preparação o Cinderace é tratado como Básico, só para o Ativo; sem mulligan.
    from ptcg.carddb import db
    from ptcg.engine import Game
    D = db()
    cin = D.resolve('Cinderace').id
    deck = [cin] * 30 + [D.resolve('Basic Fire Energy').id] * 30
    g = Game(deck, deck, seed=0, first_player=0)   # sem GameOver 'baralho sem Pokémon Básico'
    assert g.players[0].active is not None and g.players[0].active.name == 'Cinderace'
    assert not g.players[0].bench


def test_r2301_up_to_in_trainers_requires_one():
    # Ruling 2301 (+ usuário): "até X" em Treinador/Habilidade exige ao menos 1 (se houver alvo); ataque pode 0.
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Tool Scrapper'])
    board(g, 1, 'Dreepy', tools={0: ['Rescue Board']})
    at_turn(g)
    act(g, 'Tool Scrapper')
    assert 'Concluir' not in labels(g), labels(g)
    g = new_game()
    board(g, 0, 'Dreepy', hand=["N's Plan"], bench=['Dreepy'], energy={1: ['Basic Psychic Energy'] * 2})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, "N's Plan")
    assert len(g.players[0].active.energy) >= 1, g.players[0].active.energy   # a 1ª Energia é obrigatória


def test_r2142_surfer_draws_before_buzzing_boost():
    # Ruling 2142: a compra do Surfer resolve antes da Habilidade do Yanmega ex que dispara na troca.
    g = new_game()
    board(g, 0, 'Dreepy', bench=['Yanmega ex'], hand=['Surfer', 'Pikachu'],
          deck=['Pikachu'] * 4 + ['Basic Grass Energy'] * 6)
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Surfer')
    for _ in range(6):
        if g.prompt.hint == 'main':
            break
        if 'Buzzing Boost' in g.prompt.text:
            break
        g.step(0)
    assert len(g.players[0].hand) == 5 and all(c.name == 'Pikachu' for c in g.players[0].hand), \
        [c.name for c in g.players[0].hand]
    assert 'Buzzing Boost' in g.prompt.text, g.prompt.text


def test_r2154_giovanni_blocked_target_still_switches_own():
    # Ruling 2154 (+ usuário): escolhido o Cetitan ex no Banco, ele não se move, mas o jogador troca o próprio Ativo.
    g = new_game()
    board(g, 0, "Team Rocket's Kangaskhan ex", bench=["Team Rocket's Kangaskhan ex"], hand=["Team Rocket's Giovanni"],
          damage={1: 10})
    board(g, 1, 'Dreepy', bench=['Cetitan ex', 'Dreepy'])
    at_turn(g)
    act(g, 'Giovanni')
    for _ in range(6):
        if g.prompt.hint == 'gust':
            break
        g.step(0)
    assert g.prompt.hint == 'gust' and any('Cetitan' in o.label for o in g.prompt.options), labels(g)
    act(g, 'Cetitan')
    assert g.players[0].active.damage == 10, 'o próprio Ativo deve ter sido trocado'
    assert g.players[1].active.name == 'Dreepy' and any(s.name == 'Cetitan ex' for s in g.players[1].bench)



def test_r1956_mawile_invite_and_strike_no_bench_no_damage():
    # Ruling 1956: sem Pokémon no Banco do oponente não há troca e o ataque não causa dano.
    g = new_game()
    board(g, 0, 'Mawile', energy={0: ['Basic Metal Energy'] * 2})
    board(g, 1, 'Dreepy')
    g.players[0].active = None
    board(g, 0, 'TEF-112', energy={0: ['Basic Psychic Energy'] * 2})
    at_turn(g)
    act(g, 'Invite and Strike')
    assert g.players[1].active.damage == 0, g.players[1].active.damage


def test_r1949_pidove_emergency_evolution_skips_stage_1():
    # Ruling 1949: Pidove com HP restante <= 30 evolui direto para Unfezant.
    g = new_game()
    board(g, 0, 'Dreepy', bench=['TEF-133'], deck=['TEF-135'] + ['Basic Psychic Energy'] * 5, damage={1: 20})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Emergency Evolution')
    resolve_all(g)
    assert g.players[0].bench[0].name == 'Unfezant', g.players[0].bench[0].name



def test_r2025_goad_n_grab_blocked_switch_no_damage():
    # Ruling 2025: com Mist Energy a troca é prevenida e, sem novo Ativo, não há dano.
    g = new_game()
    board(g, 0, 'SCR-96', energy={0: ['Basic Darkness Energy'] * 2})
    board(g, 1, 'Dreepy', bench=['Dreepy'], energy={0: ['TEF-161']})
    at_turn(g)
    act(g, 'Goad')
    resolve_all(g)
    assert [e.name for e in g.players[1].active.energy] == ['Mist Energy'] and len(g.players[1].bench) == 1, \
        'o Ativo original (com Mist Energy) não pode ter sido nocauteado'
    assert g.players[1].active.damage == 0


def test_r2019_r2020_colorful_confection_searches_pokemon_by_basic_energy_type():
    # Rulings 2019/2020: busca Pokémon dos tipos das Energias Básicas ligadas (repetidos permitidos).
    g = new_game()
    board(g, 0, 'SCR-65', energy={0: ['Basic Psychic Energy', 'Basic Fire Energy', 'Luminous Energy']},
          deck=['SCR-60', 'ASC-20', 'ASC-20', 'Basic Fire Energy'])
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Colorful Confection')
    assert 'Basic Fire Energy' not in labels(g), labels(g)
    resolve_all(g)
    assert len([c for c in g.players[0].hand if c.d.kind == 'pokemon']) >= 1


def test_r1979_re_brew_no_counters_no_shuffle():
    # Ruling 1979: se nenhum contador é colocado (Mist Energy), as Energias ficam no descarte.
    g = new_game()
    board(g, 0, 'TWM-23', energy={0: ['Basic Psychic Energy'] * 2}, discard=['Basic Grass Energy'] * 2,
          deck=['Dreepy'] * 3)
    board(g, 1, 'Dreepy', energy={0: ['TEF-161']})
    at_turn(g)
    act(g, 'Re-Brew')
    resolve_all(g)
    assert len(g.players[0].discard) == 2 and len(g.players[0].deck) == 3, \
        (len(g.players[0].discard), len(g.players[0].deck))


def test_r2030_grand_tree_needs_valid_evolution():
    # Ruling 2030: sem Estágio 1 no deck para evoluir um Básico em jogo, Grand Tree não pode ser usado.
    g = new_game()
    board(g, 0, 'Scyther', deck=['Basic Grass Energy'] * 5)
    board(g, 1, 'Dreepy')
    g.stadium = card('Grand Tree', 0)
    at_turn(g)
    assert not has(g, 'Grand Tree'), labels(g)


def test_r2014_selective_slime_not_offered_with_all_conditions():
    # Ruling 2014: não usa se o Ativo do oponente já está Queimado, Confuso e Envenenado.
    g = new_game()
    board(g, 0, 'SCR-6')
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert has(g, 'Selective Slime'), labels(g)
    g.players[1].active.conditions = {'burned', 'confused', 'poisoned'}
    g.refresh()
    assert not has(g, 'Selective Slime'), labels(g)


def test_r2082_gravity_gemstone_cannot_raise_zero_retreat():
    # Ruling 2082: Latias ex (Skyliner) zera o Recuo; Gravity Gemstone não pode aumentá-lo.
    g = new_game()
    board(g, 0, 'Dreepy', bench=['SSP-76'])
    board(g, 1, 'Dreepy', tools={0: ['Gravity Gemstone']})
    at_turn(g)
    assert g.retreat_cost(g.players[0].active) == 0, g.retreat_cost(g.players[0].active)


def test_r2064_r2062_r2061_megaton_blower_blender_amulet():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Megaton Blower'])
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert not has(g, 'Megaton Blower'), labels(g)             # 2064: sem alvo
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Brilliant Blender'], deck=['Dreepy'] * 8)
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Brilliant Blender')
    resolve_all(g)
    assert len(g.players[0].discard) >= 2, len(g.players[0].discard)   # 2062: ao menos 1 carta descartada do baralho


def test_r2052_drag_off_no_bench_no_damage():
    g = new_game()
    board(g, 0, 'SSP-153', energy={0: ['Basic Psychic Energy'] * 2})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Drag Off')
    assert g.players[1].active.damage == 0, g.players[1].active.damage


def test_r2051_rotom_crushing_pulse_discards_tools_and_items():
    g = new_game()
    board(g, 0, 'SSP-61', energy={0: ['Basic Lightning Energy']})
    board(g, 1, 'Dreepy', hand=['Ultra Ball', 'Air Balloon', 'Basic Psychic Energy'])
    at_turn(g)
    act(g, 'Crushing Pulse')
    resolve_all(g)
    names = [c.name for c in g.players[1].hand]
    assert 'Ultra Ball' not in names and 'Air Balloon' not in names, names


def test_r2045_r1959_bench_from_top_allows_stage_1_and_2():
    g = new_game()
    board(g, 0, 'TEF-72', energy={0: ['Basic Psychic Energy'] * 3},
          deck=['Drakloak', 'Dreepy'] + ['Basic Psychic Energy'] * 8)
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Summoning Gate')
    assert 'Drakloak' in labels(g), labels(g)


def test_r2042_up_tempo_with_five_cards():
    # Ruling 2042: com 5 cartas na mão, colocar 1 no fundo deixa 4 e dá para comprar: disponível.
    g = new_game()
    board(g, 0, 'Quaquaval', hand=['Dreepy'] * 5, deck=['Dreepy'] * 5)
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert has(g, 'Up-Tempo'), labels(g)


def test_r1985_accompanying_flute_needs_opponent_bench_space():
    g = new_game()
    board(g, 0, 'Dreepy', hand=['Accompanying Flute'])
    board(g, 1, 'Dreepy', bench=['Dreepy'] * 5)
    at_turn(g)
    assert not has(g, 'Accompanying Flute'), labels(g)


def test_r1984_undulating_slice_may_place_all_counters():
    g = new_game()
    board(g, 0, 'TWM-63', energy={0: ['Basic Water Energy'] * 3}, damage={0: 50})
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Undulating Slice')
    labs = [o.label for o in g.prompt.options]
    assert '9' in labs, labs


def test_r1981_slow_crunch_cancelled_when_defender_evolves():
    g = new_game()
    board(g, 0, 'TWM-3', energy={0: ['Basic Grass Energy'] * 3})
    board(g, 1, 'Dreepy', hand=['Drakloak'])
    at_turn(g)
    act(g, 'Slow Crunch')
    act(g, 'Evoluir')                      # o oponente evolui o Defensor no turno dele
    assert g.players[1].active.name == 'Drakloak'
    act(g, 'Passar o turno')
    resolve_all(g)
    assert g.players[1].active is not None and g.players[1].active.damage < g.hp(g.players[1].active), \
        'Drakloak não pode ser nocauteado por Slow Crunch'


def test_r1977_zero_to_hero_returns_only_palafin():
    g = new_game()
    board(g, 0, 'TWM-60', bench=['Dreepy'], energy={0: ['Basic Water Energy']}, deck=['PR-SV-126', 'Pikachu'])
    g.players[0].active.cards.insert(0, card('TWM-59', 0))
    board(g, 1, 'Dreepy')
    at_turn(g)
    act(g, 'Recuar')
    for _ in range(8):
        if g.prompt.hint == 'main':
            break
        g.step(0)
    assert any(c.name == 'Palafin' for c in g.players[0].deck) and not any(c.name == 'Finizen' for c in g.players[0].deck), \
        [c.name for c in g.players[0].deck]


def test_r1975_palafin_ex_cannot_evolve_from_hand():
    g = new_game()
    board(g, 0, 'TWM-59', hand=['PR-SV-126'], energy={0: ['Basic Water Energy']})
    board(g, 1, 'Dreepy')
    at_turn(g)
    assert not has(g, 'Palafin ex'), labels(g)


def test_r2025_goad_n_grab_damages_new_active():
    g = new_game()
    board(g, 0, 'SCR-96', energy={0: ['Basic Darkness Energy'] * 2})
    board(g, 1, 'Dreepy', bench=['Dragapult ex'])
    at_turn(g)
    act(g, 'Goad')
    resolve_all(g)
    assert g.players[1].active.name == 'Dragapult ex' and g.players[1].active.damage == 160, \
        (g.players[1].active.name, g.players[1].active.damage)
    assert g.players[1].bench[0].damage == 0



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
