# PTCG Lab — motor de Pokémon TCG (regras do Pokémon TCG Live) para testar e otimizar decks

Formato: **Padrão TEF–30C** (marcas de regulamento H, I e J) — 2.083 cartas.

- **[INSTALACAO.md](INSTALACAO.md)** — passo a passo para deixar funcionando no computador e testes a rodar
- **[PLANO.md](PLANO.md)** — plano completo, o que está pronto e os próximos passos
- **[DECKS.md](DECKS.md)** — importar, limpar (fora da rotação), alterar e criar decks

## Estrutura

```
cartas/            BIBLIOTECA DE CARTAS (o que cada carta faz, em inglês e português)
  cartas.db          banco SQLite com todas as cartas, ataques, Habilidades e impressões
  Treinadores.json   Pokemon.json   Energias.json        (os 3 arquivos consolidados)
  Treinadores/Apoiadores | Itens | Ferramentas | Estadios
  Pokemon/Pokemon_EX/<Tipo>   Pokemon/<Tipo>             (Planta, Fogo, Agua, Eletrico, Psiquico,
  Energias/<Tipo>   Energias/Especiais                    Lutador, Escuridao, Metal, Dragao, Incolor)
decks/             DECKS (texto no formato do TCG Live)
  meus/  importados/  limitless/<torneio>/  _lixeira/
logs/              LOG: atividade.log, partidas do TCG Live, simulações, partidas da interface
ptcg/              o motor
  engine.py          regras (setup, turnos, ações legais, dano, condições, KO, prêmios, vitória)
  carddb.py          base de cartas (ptcg/data/cards.json + cards_pt.json)
  effects/           efeitos: Treinadores/Ferramentas/Estádios/Energias escritos à mão,
                     compilador de texto para ataques e Habilidades
  decks.py           leitura/validação de listas      limitless.py   importador da Limitless
  replay/            leitura e reprodução de logs do Pokémon TCG Live
  logbook.py         LOG               agents.py / ai/   IA (heurística e rede PyTorch)
cartas.py          consulta à biblioteca de cartas
gerenciar_decks.py criar / importar / montar / editar / exportar / validar decks
gerenciar_logs.py  guardar e consultar logs (TCG Live, simulações, atividade)
import_limitless.py baixar top 8 de torneios da Limitless
replay_log.py      reproduzir logs do TCG Live no motor
simulate.py        matriz de confrontos      optimize.py   otimizar uma lista
server.py + web/   interface gráfica local (http://localhost:8765)
tools/             reconstrução da base de cartas (build_carddb, build_pt_texts, export_cartas)
tests/             regras, fuzzing, logs reais do TCG Live, importador
```

## Uso rápido

Python 3.10+ e numpy (`pip install -r requirements.txt`; PyTorch só para treinar a rede).

```
python cartas.py buscar "Ultra Bola"                 # consultar cartas
python cartas.py mostrar TWM-130

python gerenciar_decks.py criar meu_deck --arquivo lista.txt     # lista exportada do TCG Live
python gerenciar_decks.py montar meu_deck                         # montagem interativa
python gerenciar_decks.py listar
python import_limitless.py import --latest 5                      # top 8 dos últimos torneios

python gerenciar_logs.py importar partida.txt        # log do TCG Live ("Copy Log") → guardado e reproduzido
python simulate.py meus/meu_deck limitless/2026-08-worlds/01_hedrick_dragapult --games 200 --salvar-log
python optimize.py meus/meu_deck --gauntlet 01_hedrick_dragapult 05_heiremans_crustle
python server.py                                     # interface: jogar, assistir IA, reproduzir logs
```

## Logs do Pokémon TCG Live

No TCG Live, no histórico da partida, use **Copy Log** e salve o texto em um arquivo (ou cole na interface
em *Log do TCG Live…*). O motor refaz cada jogada, confere os danos com o log oficial e aponta onde as
regras divergem. Os 4 logs de exemplo em `tests/fixtures/ptcgl_logs` são reproduzidos 100%
(`python tests/test_replay.py`). Esses logs também viram dados de treino por imitação
(`python gerenciar_logs.py imitacao dados/imitacao.pkl`).

## Cobertura de cartas

`python cartas.py resumo` mostra o estado atual. Todos os Treinadores, Ferramentas, Estádios e Energias
estão implementados, assim como todas as cartas dos decks top 8 importados. Uma parte dos Pokémon tem
ataques/Habilidades raros ainda parciais — cada ficha (`cartas.py mostrar`, campo `simulador`) diz o que falta.

## Testes

```
python tests/test_rules.py     python tests/test_engine.py     python tests/test_replay.py
python tests/fuzz.py --games 300                                python tests/test_limitless.py
```
