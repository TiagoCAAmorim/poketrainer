# CLAUDE.md — poketrainer (PTCG Lab)

Motor de regras de Pokémon TCG (regras do Pokémon TCG Live) em Python, para testar e otimizar decks
competitivos e, depois, treinar uma IA (PyTorch). **O usuário fala português (pt-BR): responda em português.**
Mensagens do motor, logs e CLIs estão em português; nomes de cartas ficam em inglês (oficial) com nome pt ao lado.

## Objetivos do usuário (em ordem de prioridade)
1. **Motor**: todas as cartas do formato Padrão atual (TEF–30C, marcas H/I/J, 2.083 cartas) funcionando.
2. **Decks**: montar vários, importar listas (TCG Live/Limitless) e baixar top 8 de Regionais/Internacionais/Mundial
   da Limitless (`import_limitless.py`, `ptcg/limitless.py`).
3. **Validação com partidas reais do TCG Live**: logs "Copy Log" reproduzidos jogada a jogada (`ptcg/replay/`).
   Vídeos foram substituídos por esses logs. O usuário NÃO terá logs novos (sem repositório público): validar por Compendium, interface e testes.
4. **Biblioteca de cartas** (`cartas/`), **gerenciador de decks** e **LOG** (`logs/`).
5. Interface HTML local (`server.py` + `web/index.html`) e IA (`ptcg/agents.py`, `ptcg/ai/`) — secundárias por ora.

## Arquitetura do motor (ptcg/)
- `engine.py` — `Game`: a partida inteira é um **gerador** que produz `Prompt(player, hint, text, options)`;
  `g.step(i)` escolhe a opção i. Prompts de opção única se resolvem sozinhos. Determinístico por `seed` +
  `history` (lista de índices) → `Game.clone()` refaz por replay. `g.refresh()` recalcula as opções da fase principal.
- **Ganchos** (`fold`/`allowed`/`anyhook`) e **eventos** (`emit`), vindos de Estádio, efeitos temporários
  (`add_effect(..., duration='opp_next_turn'|'my_next_turn'|'this_turn', while_active=...)`), Habilidades,
  Ferramentas e Energias Especiais. Lista de ganchos/eventos no topo de `engine.py`.
  Assinaturas: `damage_out(g, src, dmg, ctx, target)`, `damage_in(g, src, dmg, ctx, target, active)`,
  `can_attack(g, src, slot, attack)`, `can_play(g, src, player, card)`, `hp(g, src, value, slot)` etc.
- Energia como unidades (`frozenset` de tipos); custo pago por backtracking (`can_pay`).
- `carddb.py` — base (`ptcg/data/cards.json` + `cards_pt.json`), `db()` singleton, `resolve(nome, set, num)`,
  `named()` aceita nomes em inglês ou português.
- `effects/` — `trainers.py`, `tools.py`, `stadiums.py`, `energies.py` (todos escritos à mão),
  `abilities.py` (biblioteca de passivas por regex + escritas à mão), `attacks.py` (à mão),
  `compiler.py` (texto do ataque → passos `pre`/`post`; `count_expr`, `cond_expr`, `@pattern(regex, fase)`).
  Ordem: implementação à mão → compilador. Frase não reconhecida → carta `partial`/`missing`.
- `replay/` — `parse.py` (templates en/pt do log do TCG Live), `replay.py` (`ReplayGame` com cartas ocultas
  "UNKNOWN" que viram a carta certa sob demanda, pontos de ambiguidade com retrocesso, conferência de dano e KO).
- `decks.py`, `deckbuilder.py` (montador, `web/decks.html`), `explorer.py` (cartas, `web/cartas.html`; imagens por `baixar_imagens.py` em `imagens/`, no gitignore), `limitless.py`, `logbook.py` (LOG), `agents.py`, `encode.py` (observação p/ rede), `ai/`, `sim.py`, `view.py`.

## Comandos
```
python cartas.py buscar|mostrar|listar|resumo|atualizar     # biblioteca (gera cartas/cartas.db se faltar)
python gerenciar_decks.py listar|mostrar|criar|montar|importar|editar|copiar|exportar|validar|apagar|limitless
python gerenciar_logs.py importar|listar|mostrar|rever|atividade|reprocessar|imitacao
python replay_log.py tests/fixtures/ptcgl_logs/*.log
python simulate.py <deck> <deck> --games 200 [--salvar-log]      python optimize.py <deck> --gauntlet ...
python melhorar_heuristica.py [--avaliar|--resetar]              # ajusta pesos da heurística vs aleatório → ptcg/data/heuristica.json
python server.py                                                  # http://localhost:8765 (welcome; /jogar /decks /cartas)
python baixar_imagens.py                                          # imagens das cartas → imagens/ (fora do git)
python imitar.py gerar|treinar|avaliar                           # IA: pré-treino imitando a heurística
python train.py --resume checkpoints/imitacao.pt                 # IA: PPO self-play
python ia.py historico|acompanhar                                 # IA: treinos registrados / curva do PPO (docs/IA_TREINO.md)
```
Reconstruir a base quando sair coleção nova: `python tools/build_carddb.py` (clona pokemon-tcg-data e TCGdex em
`.cache/`), `python tools/build_pt_texts.py`, `python cartas.py atualizar`.

## Testes (rodar antes de commitar mudanças no motor)
```
python tests/test_rules.py      # cenários de regras (helpers em tests/helpers.py)
python tests/test_engine.py     # partidas com os decks reais + invariantes + determinismo
python tests/test_replay.py     # os 4 logs reais do TCG Live devem reproduzir 100%
python tests/fuzz.py --games 300  # decks aleatórios legais, invariantes a cada decisão
python tests/test_limitless.py
python tests/test_partidas_usuario.py  # partidas da interface SEM comentários (logs/interface + tests/fixtures/partidas) refeitas com invariantes
python tests/test_efeitos_novos.py # cenários da 2ª leva de cobertura
python tests/smoke_cartas.py       # todo ataque/Habilidade ativada roda sem erro
python tests/fuzz.py --games 300 --novas  # decks favorecendo a 2ª leva
python tests/test_explorer.py      # filtros/detalhe da página de cartas (ptcg/explorer.py + web/cartas.html)
python tests/test_deckbuilder.py   # montador de decks (ptcg/deckbuilder.py + web/decks.html)
python tests/test_heuristica.py    # heurística ganha ≥85% do aleatório nos decks de decks/tests
python tests/test_ai.py            # IA: formato compacto = collate, imitação e passo PPO (pula sem torch)
```
pytest não é necessário (cada arquivo roda sozinho), mas os testes são compatíveis com pytest.

## Estado atual (2026-10-17)
- Cobertura: 2.083/2.083 cartas completas (`python cartas.py resumo`). Segunda leva em `ptcg/effects/extra.py`
  (padrões `@pattern` + `*_fallback` de contagens/condições, frases compostas "A, and B" via `register_multi`),
  `abilities2.py` (Habilidades à mão: ganchos, eventos, gatilhos de movimento, `kind='hand'`/`'setup'`) e `attacks2.py`.
  Ganchos novos no motor: `can_evolve`, `ignore_effects`, `no_return_to_hand`, `trainer_fizzle`, `retreat_fizzle`,
  `keep_confusion`; `AttackImpl.cost_mod`; `AbilityImpl.hand_blocked`; `Game.prize_log`, `slot.flags['atk_log'/'dmg_log']`.
  Cuidado em regex de `@pattern`: um `(.+)` final engole o ponto (use `(.+?)`). Efeitos que pedem decisão com cartas fora
  de zona devem colocá-las em `limbo` (invariante de 60 cartas).
  Todos os Treinadores/Ferramentas/Estádios/Energias e os 12 decks fixos de `decks/tests/` (usados por `tests/test_engine.py`) estão 100%.
  `decks/limitless/` é local (gitignore): importe com `import_limitless.py` e limpe com `limpar_decks.py`; guia em `DECKS.md`.
- Replays: 4/4 logs de exemplo reproduzidos por completo, sem ajuste de dano. (Slowking copiando Metallic Hammer dá 300 sem
  Energia Metal: é o ruling oficial do Compendium, já implementado no padrão "You may discard N Energy ... more damage".)
- IA (PyTorch 2.14 + CUDA, RTX 4070 Ti SUPER de 16 GB **compartilhada** com outros projetos do usuário, ex.: `~/dev/graph_nn`):
  `ptcg/ai/dataset.py` (partidas da heurística em paralelo → shards `.npz` compactos; `ObsPacker`/`PackedObs`),
  `ptcg/ai/imitate.py` (pré-treino por imitação + `evaluate_parallel` na CPU), `ptcg/ai/train.py` (PPO com rollouts em
  workers `spawn` e atualização na GPU). Dados em `dados/imitacao/`, redes em `checkpoints/` (ambos no gitignore).
  Se a VRAM acabar, o WSL transborda para a RAM e o treino quase para: confira `nvidia-smi` antes de culpar o código.
  Guia em `docs/IA_TREINO.md`; ao terminar um experimento, registre números e conclusão em `docs/IA_PROGRESSO.md`
  (cada execução já grava em `logs/ia/treinos.jsonl`, versionado, e no W&B tiago-amorim/poketrainer no servidor da
  CoreWeave — `ptcg/ai/wb.py`; `--sem-wandb` desliga; `tests/test_ai.py` não abre execuções; para testar as CLIs use `WANDB_MODE=offline`).

## Próximos passos
0. Cobertura está em 100% (texto reconhecido); o foco agora é **fidelidade**: reproduzir logs reais e conferir cartas da 2ª leva.
1. (histórico) **Cobertura**: implementar as frases restantes (lista: script abaixo). Priorizar cartas competitivas
   (Bloodmoon Ursaluna ex "Seasoned Skill", Iron Thorns ex "Initialization", Flutter Mane "Midnight Fluttering",
   Gastrodon "Sticky Bind", Incineroar ex "Hustle Play", Munkidori ex, Kyurem "Plasma Bane", Hydreigon ex,
   Gengar ex "Gnawing Curse", Palafin "Zero to Hero", Klinklang, Okidogi "Adrena-Power", Rotom ex "Multi Adapter").
   Padrões genéricos que resolvem várias de uma vez: "Torment/Memory Lock" (escolher ataque que não pode ser usado),
   "use opponent's attack as this attack" (Foul Play/Metronome), "Discard all Energy ... does N damage to 1 of
   your opponent's Pokémon", "Round", contra-ataques "if this Pokémon is damaged ... put N damage counters",
   "Choose a random card from your opponent's hand ... shuffles it into their deck", nocaute direto ("is Knocked Out").
   ```
   python -c "from ptcg.carddb import db
   for d in db().cards.values():
       for a in d.attacks + d.abilities:
           if a.impl is None or a.impl.status != 'ok': print(d.id, d.name, '|', a.name, '|', a.impl.note if a.impl else '-')"
   ```
2. Auditar cartas dos decks competitivos contra o Compendium e tratar os problemas da interface (sem logs próprios do usuário).
3. IA: imitação e PPO longo feitos (nov/2026: `ppo4` com 85% contra a heurística; ver `docs/IA_PROGRESSO.md`).
   Próximo: continuar com `--games 960` medindo por confronto direto (`imitar.py avaliar a.pt --oponente model:b.pt`);
   decidir só com ≥ 1000 partidas (a avaliação embutida de 200 engana).

## Problemas apontados nas partidas (fluxo)
- Na interface (`/jogar`) o botão **💬 Comentar** grava um comentário na decisão atual em `logs/problemas.jsonl`
  (versionado; status `aberto`/`corrigido`, com decks, semente e decisões até ali → reproduzível).
  Partidas com comentário ficam fora de `tests/test_partidas_usuario.py`; as sem comentário viram teste do motor
  (`python gerenciar_logs.py fixar` copia as boas para `tests/fixtures/partidas/`).
- Hook `SessionStart` (`.claude/settings.json` → `tools/problemas_pendentes.py --sessao`): na **1ª sessão de cada dia**
  injeta no contexto a lista de problemas abertos. Quando aparecer, **apresente a lista ao usuário e proponha tratá-los**.
- Ao corrigir: escreva um cenário em `tests/test_rules.py`, rode os testes e então
  `python gerenciar_logs.py corrigir <ID> --nota "o que mudou"`. Consultar: `problemas [abertos|corrigidos|todos]`, `problema <ID>`.

## Convenções
- **Dúvidas de regra/implementação de uma carta**: consulte o Compendium do Pokégym
  (`https://compendium.pokegym.net/category/3-attacks/<ataque>/`; há categorias por tipo de carta) antes de supor bug do cliente.
- **Mantenha `PLANO.md` atualizado** (status das fases, números de cobertura, próximos passos) ao concluir uma etapa;
  `INSTALACAO.md` é o guia de instalação/testes do usuário — atualize se comandos ou resultados esperados mudarem.
- Não reescrever arquivos gerados à mão: `cartas/` vem de `tools/export_cartas.py`; `ptcg/data/*.json` de `tools/`.
- Correções de texto oficial vão em `ptcg/data/errata.json` (só com fonte confiável — já houve um falso positivo).
- Novos efeitos: preferir padrão genérico no compilador (`@pattern`) a código por carta; escrever à mão
  (`@attack('Carta', 'Ataque')`, `@ability('Nome')`, `@trainer('Nome')`) quando o efeito é único.
- Todo efeito novo deve passar no fuzz (`tests/fuzz.py`) e, se possível, ganhar um cenário em `tests/test_rules.py`.
