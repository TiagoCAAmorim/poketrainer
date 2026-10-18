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
- ⏸ **Logs das suas partidas** — envie alguns (`gerenciar_logs.py importar`) para encontrar regras que divergem
- ⬜ Corrigir cada divergência encontrada e transformar o log em teste automático
- ✅ Metallic Hammer copiado por Slowking (Seek Inspiration): não era bug do cliente. O ruling do Compendium (compendium.pokegym.net) diz que o
  "pode descartar" vale sem Energia Metal; o motor agora dá o dano extra e o log reproduz os 300 sem ajuste
- 🟡 Fonte para dúvidas de implementação: https://compendium.pokegym.net (rulings por carta/ataque)

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

## Fase 8 — IA que aprende ⬜
- ✅ Codificação do estado e das opções para a rede (`ptcg/encode.py`) e rede política/valor (`ptcg/ai/model.py`)
- ⬜ Instalar PyTorch e testar o treino (`train.py`) — não foi possível no ambiente anterior
- ⬜ Pré-treino por imitação a partir dos logs do TCG Live (`gerenciar_logs.py imitacao`)
- ⬜ Treino por self-play (PPO) contra a heurística e versões anteriores
- ⬜ Usar a rede treinada no `simulate.py` / `optimize.py` (`--agent model:checkpoints/best.pt`)

---

## Próximos passos (ordem sugerida)

1. **Você:** instalar e rodar os testes no computador — ver [INSTALACAO.md](INSTALACAO.md).
2. **Você:** salvar 2 a 5 logs das suas partidas no TCG Live e importar (`python gerenciar_logs.py importar …`).
3. **Claude:** conferir a fidelidade dos efeitos da 2ª leva de cobertura (a cobertura de texto já está em 100%) e tratar os problemas abertos em `logs/problemas.jsonl`.
4. **Claude:** corrigir as divergências que aparecerem nos seus logs (Fase 4).
5. **Você + Claude:** montar o gauntlet de decks a testar com os torneios já baixados (Fase 6).
6. **Claude:** melhorar a IA heurística (Fase 6) e depois iniciar o treino da rede (Fase 8).

## Como acompanhar
- Este arquivo é atualizado a cada etapa concluída.
- `python cartas.py resumo` mostra a cobertura de cartas a qualquer momento.
- `python gerenciar_logs.py atividade` mostra o que foi feito recentemente no sistema.
- Histórico de mudanças: commits no GitHub (`git log`).
