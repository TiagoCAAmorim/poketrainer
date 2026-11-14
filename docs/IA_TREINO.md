# Treino da IA — como funciona e como rodar

A IA é uma rede neural de **política/valor** (não é um modelo de linguagem): a cada decisão ela recebe o estado da
partida e as opções legais, dá uma nota para cada opção e estima quem está ganhando. Ela aprende em duas etapas:

1. **Imitação** — copia a IA heurística (`ptcg/agents.py`) a partir de milhões de decisões dela. Rápido e dá um ponto
   de partida que já sabe jogar.
2. **PPO (self-play)** — joga milhares de partidas contra si mesma, contra a heurística e contra versões antigas, e
   reforça as jogadas que deram resultado melhor que o esperado.

Histórico dos experimentos e resultados: [`IA_PROGRESSO.md`](IA_PROGRESSO.md). Registro automático de cada
treino/avaliação: `logs/ia/treinos.jsonl` (`python ia.py historico`) e, com gráficos, no **W&B**
([tiago-amorim/poketrainer](https://forge.coreweave.com/wandb/tiago-amorim/poketrainer), seção 6).

---

## Comandos

Pré-requisito: PyTorch instalado (`pip install torch`; com GPU NVIDIA, a versão CUDA). Conferir com
`python tests/test_ai.py` (3 linhas `ok`).

| Passo | Comando | Tempo (32 núcleos + RTX 4070 Ti SUPER) | Gera |
|---|---|---|---|
| 1. Dados | `python imitar.py gerar --partidas 20000` | ~2–3 min | `dados/imitacao/shard_*.npz` (~5 GB, ~3,2 milhões de decisões) |
| 2. Imitação | `python imitar.py treinar --epocas 6` | ~10 min | `checkpoints/imitacao.pt` (+ `imitacao_ultimo.pt`, `imitacao.jsonl`) |
| 3. Avaliar | `python imitar.py avaliar checkpoints/imitacao.pt --partidas 400` | ~15 s | vitórias contra a heurística, por deck |
| 4. PPO | `python train.py --resume checkpoints/imitacao.pt --iterations 300` | ~35–45 min | `checkpoints/best.pt`, `latest.pt`, `train_log.jsonl` |
| 5. Acompanhar | `python ia.py acompanhar --seguir` (em outro terminal) | — | curva da execução atual, atualizada a cada 60 s |
| 6. Histórico | `python ia.py historico` | — | tudo que já foi gerado/treinado/avaliado |
| 7. Usar | `python simulate.py deck1 deck2 --agent model:checkpoints/best.pt` | — | também aparece na interface como **Rede: checkpoints/best.pt** |

`dados/` e `checkpoints/` ficam fora do git; `logs/ia/treinos.jsonl` é versionado (é o diário dos treinos).

### Opções úteis
- Decks: padrão = todos de `decks/` (inclui `decks/limitless/`). `--pasta tests` usa só os 12 fixos;
  `--decks nome1 nome2` escolhe decks específicos (para especializar a rede num deck).
- Mais dados: `python imitar.py gerar --partidas 20000 --seed 2` acrescenta shards (use outra `--seed`).
- Continuar um PPO: `python train.py --resume checkpoints/latest.pt ...` (o otimizador recomeça; o resto continua).
- Interromper o PPO com **Ctrl+C** é seguro: salva `checkpoints/latest.pt` e registra o fim no histórico.
- Pasta de saída do PPO: `--out checkpoints/experimento1` (cada pasta tem seu `train_log.jsonl`;
  `python ia.py acompanhar checkpoints/experimento1/train_log.jsonl`).

---

## 1. O que a rede vê e como escolhe

**Entrada** (`ptcg/encode.py`), só o que o jogador da vez enxerga:
- **Mesa**: 18 posições (Ativo + 8 de Banco de cada lado), cada uma com carta, Ferramenta, PS, dano, Energias,
  condições especiais, estágio, custo de recuo, se pode evoluir, se consegue pagar o ataque, se tem Habilidade usável.
- **Mão**: as minhas cartas; do oponente, só a quantidade.
- **Descarte**: contagem de cada carta dos dois lados.
- **Globais**: tamanho dos decks, Prêmios restantes, turno, Apoiador/Energia/recuo já usados, Estádio, tipo de decisão.
- **Cada opção**: carta envolvida, Pokémon alvo, tipo de ação, dano estimado (para ataques).

**Rede** (`ptcg/ai/model.py`):
1. Cada carta vira um vetor aprendido (*embedding*): cartas com papel parecido ficam com vetores parecidos.
2. O estado é resumido num vetor de 256 números.
3. Cada opção legal recebe uma nota (estado × opção); um *softmax* entre as opções legais vira probabilidade.
   Como a rede avalia cada opção em vez de ter uma lista fixa de ações, carta nova não muda a arquitetura.
4. A **cabeça de valor** dá um número entre −1 (perdendo) e +1 (ganhando).

O motor só oferece opções legais, então a rede nunca precisa aprender as regras — só a estratégia.

## 2. Etapa 1 — imitação da heurística

**Geração dos dados** (`ptcg/ai/dataset.py`, `imitar.py gerar`):
- Partidas heurística × heurística com pares de decks sorteados, em paralelo (um processo por núcleo).
- Em cada decisão com 2+ opções grava: a observação, a opção que a heurística escolheu (**rótulo**) e o resultado
  final da partida para quem decidiu (+1/−1/0).
- **Epsilon (5%)**: a jogada *executada* é aleatória, mas o rótulo continua sendo o da heurística. Assim a rede vê
  posições fora da "linha perfeita" e aprende como sair delas (sem isso ela não saberia se recuperar de um erro).
- Formato compacto: descarte esparso, float16/int16 → ~1,8 KB por decisão (contra 20 KB sem compactar).
- Partidas com erro do motor são descartadas e anotadas em `dados/imitacao/erros.jsonl` (devem ser zero).

**Treino** (`ptcg/ai/imitate.py`, `imitar.py treinar`), supervisionado, na GPU:
- **Política**: entropia cruzada — "dê probabilidade alta à opção da heurística".
- **Valor**: erro quadrático contra o resultado da partida, com **`detach`**: essa perda treina só a cabeça de valor,
  sem alterar o resto da rede. As ~160 decisões de uma partida têm o mesmo rótulo; sem o `detach` a rede decorava as
  partidas (erro de validação subindo) e a política piorava (38% contra 44% de vitórias).
- 5% dos shards ficam separados para validação; o checkpoint salvo é o da melhor época na validação.

**Leitura**: `val_acc` = fração das decisões em que a rede escolhe o mesmo que a heurística (o teto fica abaixo de
100% porque a heurística desempata no sorteio). `val_mse_v` deve cair (abaixo de 1,0 = melhor que chutar 0).
A rede imitadora ganha menos que a heurística: pequenos desvios se acumulam ao longo da partida.

## 3. Etapa 2 — PPO (self-play)

Cada **iteração** (`ptcg/ai/train.py`):

**a) Rollout — jogar** (30 processos na CPU, cada um com uma cópia da rede):
- `--games` partidas (padrão 240). Oponente sorteado por partida: 25% heurística (`--p-heuristic`), 15% versões
  antigas da rede (`--p-pool`), o resto a própria rede.
- A rede **sorteia** a jogada pelas probabilidades (explora alternativas) e grava observação, jogada, probabilidade
  (`logp`) e valor previsto.

**b) Crédito — quão boa foi cada jogada**:
- **Recompensa**: +1 vitória / −1 derrota no fim, mais +0,05 a cada Prêmio de vantagem ganho (`--shaping`).
- **Vantagem (GAE, `--gamma 0.997`, `--lam 0.95`)**: o que aconteceu depois da jogada menos o que o valor previa.
  Positiva → a jogada foi melhor que o esperado.

**c) Atualização** (GPU, `--epochs 3` passadas sobre as ~30 mil decisões):
- **Política (PPO "recortado")**: aumenta a probabilidade das jogadas com vantagem positiva e diminui as negativas,
  limitando a mudança a ±20% (`--clip`) — impede que uma iteração de sorte estrague a rede.
- **Valor**: aprende a prever o retorno real (`--vf-coef`).
- **Entropia**: incentivo pequeno para continuar explorando (`--ent-coef`).

**d) Acompanhamento**:
- A cada 20 iterações (`--snapshot-every`) a rede entra no grupo de versões antigas (até 5, `--pool-size`).
- A cada 10 iterações (`--eval-every`) joga `--eval-games` partidas (padrão 200) contra a heurística escolhendo
  sempre a opção mais provável, com sementes fixas (comparável entre iterações). A melhor vira `best.pt`.
- Tudo vai para `train_log.jsonl` (1 linha por iteração) e as avaliações para `logs/ia/treinos.jsonl`.

## 4. Como ler o acompanhamento (`python ia.py acompanhar`)

| Coluna | Significado | Saudável |
|---|---|---|
| `aval.` | vitórias contra a heurística na avaliação | **deve subir** — é o critério principal; > 0,5 = melhor que a heurística |
| `treino` | média móvel (10 its) contra a heurística durante o treino, com sorteio | ruidoso, só indicativo |
| `kl` | quanto a política mudou na iteração | < 0,02. Acima de 0,03 → instável: baixe `--lr` |
| `clip` | fração de jogadas que bateram no limite de ±20% | ~0,02–0,10 |
| `ent` | o quanto a rede ainda hesita entre opções | cai devagar. Despencar cedo → parou de explorar: suba `--ent-coef` |
| `v` | erro da cabeça de valor | deve cair |
| `trans.` | decisões da rede na iteração | ~30 mil com os padrões |

O erro padrão de uma avaliação com 200 partidas é ~3,5 pontos percentuais: diferenças menores que isso são ruído.
O `ia.py acompanhar` mostra alertas (KL alto, erros do motor, entropia muito baixa) no fim.

## 5. Desempenho e cuidados

- Rollout ~3,5 s + atualização ~2,7 s por iteração (240 partidas). A versão antiga (1 processo) levaria ~70 s só no rollout.
- **GPU compartilhada**: se outro programa (ex.: `~/dev/graph_nn`) ocupa a memória de vídeo, no WSL/Windows ela
  transborda para a RAM e o treino quase para. Sintoma: `passos/s` caindo no `imitar.py treinar` ou iterações que
  não terminam. Confira `nvidia-smi`; feche o outro programa ou use `--device cpu` (bem mais lento na atualização).
- Base de cartas nova (outro tamanho de vocabulário): dados e checkpoints antigos não servem; gere de novo.
- Mudanças em `ptcg/encode.py` também invalidam dados e checkpoints (a entrada da rede muda).

## 6. W&B (Weights & Biases)

Todo `imitar.py gerar|treinar|avaliar` e `train.py` abre uma execução no W&B, projeto
**tiago-amorim/poketrainer** (servidor da CoreWeave, conforme o `wandb login` da máquina):
https://forge.coreweave.com/wandb/tiago-amorim/poketrainer

| `job_type` | O que é registrado |
|---|---|
| `dados` | configuração da geração (decks, epsilon, seed) e resumo (partidas, decisões, erros do motor) |
| `imitacao` | `treino/*` a cada 500 passos (perda, acerto parcial, passos/s, lr), `val/*` por época, `aval/*` no fim, tabela de vitórias por deck e o checkpoint como artefato `imitacao` |
| `avaliacao` | vitórias, erro padrão, vitórias indo primeiro e tabela por deck |
| `ppo` | `treino/*` por iteração (kl, clip, ent, v, pi, vitórias no treino contra a heurística e contra o pool, `var_explicada` do valor — perto de 1 é bom, ≤0 o valor não ajuda —, `grad_norm`, `ret_medio`, `adv_std`, decisões e turnos por partida, fração de empates e de partidas no limite de decisões, lr, tempos, pico de VRAM), `aval/*` a cada avaliação (eixo = iteração) e o `best.pt` como artefato `ppo` (aliases `best` e a data da execução) |

- A URL da execução também vai para `logs/ia/treinos.jsonl` (campo `wandb`).
- `--sem-wandb` desliga; `--nome` dá nome à execução (padrão do PPO: `ppo_<data>`).
- Sem internet: `WANDB_MODE=offline python train.py ...` e depois `wandb sync wandb/offline-run-*`.
- Outra entidade/projeto: `WANDB_ENTITY=... WANDB_PROJECT=...`. Sem o pacote `wandb` ou sem login, o treino roda
  normalmente e só avisa. A pasta local `wandb/` fica fora do git.

## 7. Arquivos

| Arquivo | Papel |
|---|---|
| `ptcg/encode.py` | estado e opções → arrays numpy |
| `ptcg/ai/model.py` | rede política/valor, `collate`, salvar/carregar checkpoint |
| `ptcg/ai/dataset.py` | geração paralela dos dados de imitação; `ObsPacker`/`PackedObs` (formato compacto e lotes) |
| `ptcg/ai/imitate.py` | treino por imitação; `evaluate_parallel` (avaliação contra heurística/aleatório) |
| `ptcg/ai/train.py` | PPO: rollouts em processos, GAE, atualização, avaliações, registro |
| `ptcg/ai/wb.py` | registro no W&B (no-op se desligado/indisponível) |
| `ptcg/ai/agent.py` | `TorchAgent` — usa a rede para jogar (`make_agent('model:...')`) |
| `imitar.py`, `train.py`, `ia.py` | linhas de comando |
| `tests/test_ai.py` | formato compacto = `collate`, imitação, rollout + passo PPO |
