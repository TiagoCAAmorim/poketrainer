# Documentação técnica

Para instalar e usar, veja o [README](../README.md). Comandos: [COMANDOS.md](COMANDOS.md).

## Estrutura de pastas

```
cartas/            BIBLIOTECA DE CARTAS (o que cada carta faz, em inglês e português)
  cartas.db          banco SQLite com cartas, ataques, Habilidades e impressões (gerado; fora do git)
  Treinadores.json   Pokemon.json   Energias.json        (os 3 arquivos consolidados)
  Treinadores/Apoiadores | Itens | Ferramentas | Estadios
  Pokemon/Pokemon_EX/<Tipo>   Pokemon/<Tipo>             (Planta, Fogo, Agua, Eletrico, Psiquico,
  Energias/<Tipo>   Energias/Especiais                    Lutador, Escuridao, Metal, Dragao, Incolor)
imagens/           imagens das cartas baixadas (fora do git)
decks/             DECKS (texto no formato do TCG Live)
  meus/  importados/  limitless/<torneio>/  tests/ (12 decks fixos dos testes)  _lixeira/  _fora_da_rotacao/
logs/              LOG: atividade, partidas do TCG Live, simulações, partidas da interface, problemas.jsonl, ia/treinos.jsonl
ias/               IAs treinadas por nível de dificuldade (nivel_4.pt … nivel_9.pt, niveis.json, confrontos.md) — versionadas
checkpoints/ dados/  treino da IA (fora do git)
pdfs/              PDFs de impressão (fora do git)
ptcg/              o motor
web/               páginas da interface (welcome, index = /jogar, decks, cartas, testar, imprimir)
site/              página ESTÁTICA do PDF de cartas simplificadas (HTML+JS, sem servidor; ver site/LEIAME.md)
tools/             reconstrução da base de cartas (build_carddb, build_pt_texts, export_cartas)
tests/             regras, fuzzing, logs reais do TCG Live, importador, interface
```

## O motor (`ptcg/`)

- `engine.py` — `Game`: a partida inteira é um **gerador** que produz `Prompt(player, hint, text, options)`;
  `g.step(i)` escolhe a opção i. Prompts de opção única se resolvem sozinhos. Determinístico por `seed` +
  `history` (lista de índices); `Game.clone()` refaz por replay.
- **Ganchos** (`fold`/`allowed`/`anyhook`) e **eventos** (`emit`) vindos de Estádios, efeitos temporários
  (`add_effect(..., duration=...)`), Habilidades, Ferramentas e Energias Especiais. Lista no topo de `engine.py`.
- Energia como unidades (`frozenset` de tipos); custo pago por backtracking (`can_pay`).
- `carddb.py` — base (`ptcg/data/cards.json` + `cards_pt.json`); `named()` aceita nomes em inglês ou português.
- `effects/` — `trainers.py`, `tools.py`, `stadiums.py`, `energies.py` (à mão), `abilities.py`/`abilities2.py`,
  `attacks.py`/`attacks2.py` (à mão), `compiler.py` e `extra.py` (texto do ataque → passos, via `@pattern`).
  Ordem: implementação à mão → compilador. Frase não reconhecida → carta `partial`/`missing`.
- `replay/` — leitor de logs do TCG Live (en/pt) e `ReplayGame`, com cartas ocultas que viram a carta certa sob
  demanda, retrocesso nos pontos ambíguos, conferência de dano e KO.
- Outros: `decks.py`, `deckbuilder.py`, `explorer.py`, `imprimir.py`, `testdeck.py`, `limitless.py`, `logbook.py`,
  `agents.py` (heurística), `encode.py` (observação para a rede), `ai/` (PyTorch), `sim.py`, `view.py`.

## Cobertura de cartas

`python cartas.py resumo`: **2.083 de 2.083 cartas completas** (Pokémon, Treinadores, Ferramentas, Estádios e Energias).
"Completa" = o texto foi reconhecido e executa; a fidelidade é checada por cenários (`tests/test_rules.py`,
`test_efeitos_novos.py`, `test_rulings.py`), `tests/smoke_cartas.py` (todo ataque/Habilidade roda sem erro) e fuzz.
A validação das regras usa o Compendium do Pokégym (compendium.pokegym.net); progresso em
[RULINGS_PROGRESSO.md](RULINGS_PROGRESSO.md). Aproximações conhecidas e próximos passos: [PLANO.md](../PLANO.md).

## Testes

```
python tests/test_rules.py          # cenários de regras
python tests/test_rulings.py        # rulings do Compendium
python tests/test_engine.py         # partidas com os decks reais + invariantes + determinismo
python tests/test_replay.py         # os 4 logs reais do TCG Live devem reproduzir 100%
python tests/fuzz.py --games 300    # decks aleatórios legais, invariantes a cada decisão
python tests/test_limitless.py  tests/test_testdeck.py  tests/test_explorer.py  tests/test_deckbuilder.py
python tests/test_atualizar.py      # atualização (git local e ZIP) preservando dados do usuário
python tests/test_imprimir.py       # precisa de reportlab + pillow
python tests/test_site.py           # dados da página estática (site/data) coerentes com a base
python tests/test_partidas_usuario.py  tests/test_efeitos_novos.py  tests/smoke_cartas.py
python tests/test_heuristica.py     # heurística ganha ≥85% do aleatório
python tests/test_ai.py             # IA (pula sem torch)
```
Cada arquivo roda sozinho; também funcionam com `pytest` (`pip install -r requirements-dev.txt`).
Resultados esperados de cada um: [INSTALACAO.md](../INSTALACAO.md).

## IA

- Heurística (`ptcg/agents.py`, nível 0): regras escritas à mão, pesos em `ptcg/data/heuristica.json`.
- Redes (`ptcg/ai/`): pré-treino por imitação da heurística e depois PPO contra si mesma.
  Guia: [IA_TREINO.md](IA_TREINO.md) · diário dos experimentos: [IA_PROGRESSO.md](IA_PROGRESSO.md) ·
  treino em outra máquina: [IA_NOVO_COMPUTADOR.md](IA_NOVO_COMPUTADOR.md).
- **Níveis de dificuldade** (`ias/`): 0 = heurística, 4–9 = redes treinadas guardadas em float16 (~4,6 MB cada).
  O nível é o **Elo relativo à heurística**, ajustado a todas as avaliações registradas
  (`python ia.py niveis`; `ias/confrontos.md` é gerado, não editar à mão).
  O nível 9 (`ppo4-t3`) vence a heurística em ~85% das partidas.
- Cada execução de treino grava em `logs/ia/treinos.jsonl` (versionado) e no W&B (`--sem-wandb` desliga).
