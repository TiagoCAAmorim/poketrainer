# Plano do projeto — PTCG Lab (poketrainer)

Objetivo: um sistema para **testar e otimizar decks competitivos de Pokémon TCG**, com um motor que segue as
regras do Pokémon TCG Live, decks de torneios reais, validação com partidas reais do TCG Live e, por fim,
uma IA que aprende a jogar.

Legenda: ✅ feito · 🟡 em andamento / parcial · ⬜ a fazer · ⏸ em espera (depende de algo)

Atualizado em: 2026-10-17

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
- 🟡 Pokémon: **1.628 completas · 389 parciais · 66 pendentes**
  (`python cartas.py resumo`; a lista do que falta: `python cartas.py listar --pendentes`)
- ⬜ **Próximo:** cartas competitivas que ainda faltam — Bloodmoon Ursaluna ex (Seasoned Skill),
  Iron Thorns ex (Initialization), Flutter Mane (Midnight Fluttering), Gastrodon (Sticky Bind),
  Incineroar ex (Hustle Play), Munkidori ex, Kyurem (Plasma Bane), Hydreigon ex, Gengar ex (Gnawing Curse),
  Palafin (Zero to Hero), Klinklang, Okidogi (Adrena-Power), Rotom ex (Multi Adapter)
- ⬜ Efeitos genéricos que resolvem várias cartas de uma vez: "usar ataque do oponente como este ataque",
  "escolher um ataque que o oponente não pode usar", "descartar Energias e causar N a 1 Pokémon do oponente",
  "Round", contra-ataques ("se este Pokémon for danificado… coloque N contadores"), "carta aleatória da mão
  do oponente volta para o baralho", nocaute direto
- ⬜ Meta: 100% das cartas completas

## Fase 3 — Decks ✅
- ✅ Leitura de listas do TCG Live e da Limitless (nomes em inglês ou português, com ou sem coleção/número)
- ✅ Validação (60 cartas, até 4 cópias, ≥1 Básico, ≤1 ACE SPEC) + aviso de cartas com efeito parcial
- ✅ Importador da Limitless: top 8 de Regionais, Internacionais e Mundial (`import_limitless.py`)
- ✅ 12 decks fixos em `decks/tests/` (Mundial 2026 e Regional de Louisville 2026) usados pelos testes; `decks/limitless/` fica fora do git
- ✅ `limpar_decks.py`: separa decks com cartas fora da rotação (guia em `DECKS.md`)
- ✅ Gerenciador: criar, montar (interativo), importar, editar, copiar, exportar, validar, apagar (`gerenciar_decks.py`)
- ⬜ Baixar mais torneios recentes (Regionais/Internacionais de 2026) para ampliar o gauntlet
- ⬜ Testar o importador com o site atual da Limitless no seu computador (no ambiente anterior a rede era restrita)

## Fase 4 — Validação com partidas reais do TCG Live 🟡
- ✅ Leitor de logs "Copy Log" (inglês e português)
- ✅ Reprodução jogada a jogada no motor, conferindo danos e nocautes; retrocesso nos pontos ambíguos
- ✅ 4 logs de exemplo reproduzidos 100%
- ⏸ **Logs das suas partidas** — envie alguns (`gerenciar_logs.py importar`) para encontrar regras que divergem
- ⬜ Corrigir cada divergência encontrada e transformar o log em teste automático
- ⬜ Investigar: Metallic Hammer copiado por Slowking (Seek Inspiration) deu 300 no TCG Live sem descartar
  Energias Metal (possível bug do próprio jogo; hoje o replay ajusta o dano ao log)

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
- ⬜ Melhorias visuais (imagens das cartas, animações) — baixa prioridade por enquanto

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
3. **Claude:** implementar as cartas competitivas pendentes da Fase 2 e os efeitos genéricos.
4. **Claude:** corrigir as divergências que aparecerem nos seus logs (Fase 4).
5. **Você + Claude:** baixar torneios recentes da Limitless e montar o gauntlet de decks a testar (Fase 3).
6. **Claude:** melhorar a IA heurística (Fase 6) e depois iniciar o treino da rede (Fase 8).

## Como acompanhar
- Este arquivo é atualizado a cada etapa concluída.
- `python cartas.py resumo` mostra a cobertura de cartas a qualquer momento.
- `python gerenciar_logs.py atividade` mostra o que foi feito recentemente no sistema.
- Histórico de mudanças: commits no GitHub (`git log`).
