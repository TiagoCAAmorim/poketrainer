# Plano do projeto — PTCG Lab (poketrainer)

Objetivo: um sistema para **testar e otimizar decks competitivos de Pokémon TCG**, com um motor que segue as
regras do Pokémon TCG Live, decks de torneios reais, validação com partidas reais do TCG Live e, por fim,
uma IA que aprende a jogar.

Legenda: ✅ feito · 🟡 em andamento / parcial · ⬜ a fazer · ⏸ em espera (depende de algo)

Atualizado em: 2026-10-18

---

## Fase 1 — Motor de regras ✅ (base pronta)
- ✅ Fluxo completo da partida: preparação, mulligan, moeda, turnos, compra, fase principal, ataque, Checkup
- ✅ Ações legais: jogar Básico, evoluir, ligar Energia (1 por turno), Treinadores (1 Apoiador, 1 Estádio), Ferramentas, recuar, Habilidades, atacar
- ✅ Dano: fraqueza, resistência, modificadores, proteção do Tera no Banco, nocautes, Prêmios (ex = 2, Mega ex = 3)
- ✅ Condições especiais (Adormecido, Paralisado, Confuso, Envenenado, Queimado)
- ✅ Regras de 1º turno, limite de Banco (inclui Área Zero com 8), ACE SPEC, condições de vitória
- ✅ Partidas determinísticas e reproduzíveis (semente + sequência de decisões)

## Fase 2 — Cartas do formato (TEF–30C, marcas H/I/J) 🟡
- ✅ Base com as 2.083 cartas legais (textos oficiais em inglês e português)
- ✅ Todos os Treinadores (Itens, Apoiadores), Ferramentas, Estádios e Energias Especiais
- ✅ Todas as cartas dos 12 decks de teste (`decks/tests/`, top 8 do Mundial e de Louisville 2026)
- ✅ Pokémon: **2.083 completas · 0 parciais · 0 pendentes** (`python cartas.py resumo`). A segunda leva (451 cartas)
  está em `ptcg/effects/extra.py` (padrões do compilador), `abilities2.py` e `attacks2.py` (à mão).
  "Completa" = o texto foi reconhecido e executa; a fidelidade é checada por `tests/test_efeitos_novos.py` (cenários),
  `tests/smoke_cartas.py` (todo ataque/Habilidade ativada roda sem erro e sem perder cartas) e
  `tests/fuzz.py --novas` (decks favorecendo essas cartas).
- 🟡 Aproximações conhecidas, avaliadas contra o Compendium (compendium.pokegym.net):
  - **Multi Adapter**: "qualquer Pokémon com Rotom no nome" (ruling 2242) já está certo. Continua sem descartar Ferramentas extras ao
    perder a Habilidade (o Compendium não trata disso).
  - **Luminous Wing**: o ruling 2309 manda prevalecer sobre Initialization, o que o motor errava; corrigido (teste em `test_efeitos_novos.py`).
    Safeguard e Mysterious Rock Inn continuam valendo contra ele (rulings 2369/2335), como já era. Segue bloqueando só contadores de Habilidades.
  - **Backtrack Badge**: não vale para a checagem de Confusão (ruling 2417) e agora refaz **todas** as moedas do ataque, 1x por turno
    (ruling 2416): a oferta vem ao fim da fase `pre` do ataque compilado e, aceita, refaz toda a fase. Segue valendo só para ataques
    compilados do texto (ataques escritos à mão não oferecem o Badge).
  - **Core Memory / TM Fluorite**: o Compendium não tem rulings nem a carta (busca sem resultado); ataques seguem tirados de sites de cartas.
- ✅ Meta atingida: 100% das cartas completas e biblioteca `cartas/` regerada (2.083 `implementada`); próximo: fidelidade via logs reais

## Fase 3 — Decks ✅
- ✅ Leitura de listas do TCG Live e da Limitless (nomes em inglês ou português, com ou sem coleção/número)
- ✅ Validação (60 cartas, até 4 cópias, ≥1 Básico, ≤1 ACE SPEC) + aviso de cartas com efeito parcial
- ✅ Importador da Limitless: top 8 de Regionais, Internacionais e Mundial (`import_limitless.py`)
- ✅ 12 decks fixos em `decks/tests/` (Mundial 2026 e Regional de Louisville 2026) usados pelos testes; `decks/limitless/` fica fora do git
- ✅ `limpar_decks.py`: separa decks com cartas fora da rotação (guia em `DECKS.md`)
- ✅ Gerenciador: criar, montar (interativo), importar, editar, copiar, exportar, validar, apagar (`gerenciar_decks.py`)
- ✅ Baixar mais torneios recentes (Regionais/Internacionais de 2026) para ampliar o gauntlet
- ✅ Importador testado com o site atual da Limitless

## Fase 4 — Validação com partidas reais do TCG Live 🟡
- ✅ Leitor de logs "Copy Log" (inglês e português)
- ✅ Reprodução jogada a jogada no motor, conferindo danos e nocautes; retrocesso nos pontos ambíguos
- ✅ 4 logs de exemplo reproduzidos 100%
- ⏸ Logs próprios do TCG Live: **sem acesso a novos logs** (sem repositório público; os 4 de exemplo são tudo que há). A validação passa a
  vir dos rulings do Compendium, das partidas da interface (botão 💬 Comentar) e dos testes de cenário/fuzz
- ⬜ Se algum log novo aparecer: reproduzir, corrigir a divergência e transformar em teste (`gerenciar_logs.py importar`)
- ✅ Metallic Hammer copiado por Slowking (Seek Inspiration): não era bug do cliente. O ruling do Compendium (compendium.pokegym.net) diz que o
  "pode descartar" vale sem Energia Metal; o motor agora dá o dano extra e o log reproduz os 300 sem ajuste
- ✅ Revisão de rulings, sessão 4 (fev/2026 → 2024, Fases 2–3 incluídas): ~45 correções com cenário em `tests/test_rulings.py` (Area Zero, Goad 'n' Grab, Crystal Fall/Flare Fall, Gale Thrust, Surfer, Cinderace, "até X", Giovanni/Cetitan, Gravity Gemstone, Palafin ex, Festival Lead…); o restante dos IDs é não testável (cartas fora do H/I/J). Vitória simultânea = empate (decisão do usuário).
- ✅ Revisão de rulings do Compendium (jul–mar/2026, 85 IDs; progresso em `docs/RULINGS_PROGRESSO.md`): 18 divergências corrigidas com cenário
  em `tests/test_rulings.py` (Bastiodon/Ancient Bulwark, Mist Energy e Hide 'n' Sneak em efeitos atrasados e de Habilidade, Erasure Ball,
  Sand Attack antes da Confusão, Pleasing Present simultâneo, etc.). Mecanismos novos no motor: remoção de Energia adiada para depois do
  dano (`ctx.data['after']`), `Game.effects_prevented_from`, gancho `damage_out_bench`. Faltam fev/2026 e anteriores.
- 🟡 Fonte principal de validação agora: https://compendium.pokegym.net (rulings por carta/ataque), conferindo as cartas dos decks competitivos

## Fase 5 — Biblioteca de cartas e LOG ✅
- ✅ `cartas/`: banco SQLite + Treinadores.json / Pokemon.json / Energias.json + pastas
  (Apoiadores, Itens, Ferramentas, Estádios · Pokémon EX por tipo · Pokémon por tipo · Energias por tipo · Especiais)
- ✅ Consulta: `cartas.py buscar | mostrar | listar | resumo | atualizar`
- ✅ LOG em `logs/`: atividade, partidas do TCG Live, simulações (reproduzíveis), partidas da interface
- ✅ `gerenciar_logs.py importar | listar | mostrar | rever | atividade | reprocessar | imitacao`

## Fase 6 — Testes de deck e otimização 🟡
- ✅ Matriz de confrontos (`simulate.py`) e otimizador de listas por troca de cartas (`optimize.py`)
- 🟡 A IA heurística ainda é simples: as taxas de vitória servem como indicação, não como verdade
- ⬜ Melhorar a IA heurística (uso de Apoiadores, sequência de turno, escolha de alvos)
- ⬜ Relatórios de confronto (por exemplo, uma página com a matriz e gráficos)

## Fase 7 — Interface gráfica 🟡
- ✅ Jogar contra a IA, assistir IA × IA, desfazer, revelar mãos, editar decks
- ✅ Botão 💬 Comentar: problemas ficam em `logs/problemas.jsonl` (abertos/corrigidos); aviso no 1º início de sessão do dia
  (hook em `.claude/settings.json`); partidas sem comentário viram teste (`tests/test_partidas_usuario.py`, `gerenciar_logs.py fixar`)
- ✅ Reproduzir logs do TCG Live jogada a jogada
- ✅ Consultor de IA para o humano (sugestões da heurística/rede, trocável na partida)
- ✅ Imagens das cartas: `baixar_imagens.py` (Limitless como 3ª fonte, opção `--manual`; `imagens/` fora do git)
- ⬜ Animações e demais melhorias visuais — baixa prioridade por enquanto

## Fase 8 — IA que aprende 🟡
Guia: `docs/IA_TREINO.md` · diário dos experimentos: `docs/IA_PROGRESSO.md` · `python ia.py historico|acompanhar`
- ✅ Codificação do estado e das opções para a rede (`ptcg/encode.py`) e rede política/valor (`ptcg/ai/model.py`)
- ✅ PyTorch 2.14 + CUDA instalado e testado (`tests/test_ai.py`)
- ✅ Pré-treino por imitação da heurística (`imitar.py gerar|treinar|avaliar`): 20.000 partidas heurística × heurística,
  5% de jogadas aleatórias com o rótulo da heurística. A perda de valor não mexe no tronco da rede (`detach_value`),
  senão o valor decora as partidas e a política piora. Refeita em 13/11/2026 com o motor e a heurística atuais
  (2,86 milhões de decisões, 780 decks): **86,0% de acerto** na validação, **46–49% contra a heurística**.
- ✅ PPO com rollouts paralelos (`train.py`): 30 processos na CPU + atualização na GPU, ~7 s por iteração de 240 partidas
  (~30 mil decisões). Teste de 10 iterações a partir da imitação: estável (KL < 0,01), 44% → 47% contra a heurística.
- ✅ Bug do motor achado pelo treino: Night Joker (N's Zoroark ex) oferecia o Night Joker de outro N's Zoroark ex no
  Banco, e a cópia se repetia sem fim; agora só os demais ataques dos N's Pokémon no Banco (teste em `tests/test_rules.py`)
- ✅ Treino PPO longo (sessão 2, 13–14/11/2026, RTX 3060 Laptop): `ppo1` 300 it → **73%**; `ppo2` +400 it → **80%**;
  platô em ~79% com 240 partidas/it, destravado com `--games 960` → `ppo4` **85% contra a heurística** (2000 partidas),
  vence o `ppo1` em 69% e o `ppo2` em 60% no confronto direto. Varredura de hiperparâmetros, rede 512, decaimento da
  lr e pool diverso não mudaram o resultado. Detalhes em `docs/IA_PROGRESSO.md`.
- ✅ Ferramentas de treino: métricas extras no W&B (variância explicada, `grad_norm`, vitórias contra o pool…),
  confronto direto entre redes (`imitar.py avaliar --oponente model:x.pt`), `train.py --lr-final` e `--pool-inicial`
- ⬜ Continuar o PPO com lote grande enquanto o confronto direto contra a versão anterior passar de 50%
- ⬜ Usar a rede treinada no `simulate.py` / `optimize.py` (`--agent model:checkpoints/best.pt`) — a ligação já existe

---

## Próximos passos (ordem sugerida)

Sem logs próprios do TCG Live, a fidelidade passa a ser validada pelo Compendium, pelas partidas da interface e pelos testes.

1. **Claude:** auditar as cartas dos decks competitivos (`decks/tests/` e `decks/limitless/`) contra os rulings do Compendium
   (compendium.pokegym.net), começando pelas mais usadas; cada divergência vira cenário em `tests/test_rules.py`.
2. **Você:** jogar partidas na interface (`/jogar`) e usar 💬 Comentar quando algo parecer errado; Claude trata os problemas abertos.
   Hoje não há nenhum aberto em `logs/problemas.jsonl`.
3. **Claude:** fechar as aproximações restantes da Fase 2: Multi Adapter (descartar Ferramentas extras ao perder a Habilidade),
   Luminous Wing (outros efeitos de Habilidades além de contadores) e Backtrack Badge em ataques escritos à mão.
   Core Memory e TM Fluorite dependem de uma fonte para conferir.
4. **Você + Claude:** montar o gauntlet com os decks de `decks/limitless/` e rodar a matriz de confrontos (`simulate.py`, Fase 6).
5. **Claude:** melhorar a IA heurística (Apoiadores, sequência de turno, escolha de alvos) e criar a página de relatórios de confronto (Fase 6).
6. **Claude:** continuar o PPO (`python train.py --resume checkpoints/ppo4/t2/latest.pt --games 960 --iterations 100`)
   e medir cada trecho por confronto direto; se estacionar, rever a observação (`encode.py`) ou acrescentar busca (Fase 8).

## Como acompanhar
- Este arquivo é atualizado a cada etapa concluída.
- `python cartas.py resumo` mostra a cobertura de cartas a qualquer momento.
- `python gerenciar_logs.py atividade` mostra o que foi feito recentemente no sistema.
- Histórico de mudanças: commits no GitHub (`git log`).
