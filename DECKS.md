# Decks — importar, limpar, alterar e criar

Todo deck é um arquivo `.txt` no formato de lista do Pokémon TCG Live (dá para colar direto no jogo).
Linhas `# chave: valor` no topo guardam metadados (evento, data, colocação, jogador, arquétipo, fonte).
Nomes de cartas em inglês ou português, com ou sem coleção/número: `4 Ultra Ball MEG 131`, `4 Ultra Bola`.

| Pasta | Conteúdo |
|---|---|
| `decks/meus/` | seus decks (`criar`, `montar`, `copiar`, interface) |
| `decks/importados/` | listas importadas de arquivos |
| `decks/tests/` | 12 decks fixos (Mundial e Louisville 2026) usados pelos testes — versionados, não mexa |
| `decks/limitless/<torneio>/` | top N de torneios da Limitless (+ `index.json` com o resumo) |
| `decks/_lixeira/` | decks apagados com `apagar` (recuperáveis) |
| `decks/_fora_da_rotacao/` | decks movidos por `limpar_decks.py` (recuperáveis) |

Pastas que começam com `_` são ignoradas em listagens e simulações. `decks/limitless/`, `_lixeira/` e `_fora_da_rotacao/`
estão no `.gitignore`; `tests/test_engine.py` usa só `decks/tests/`, então não depende do que você importou.

## 1. Importar

**Torneios da Limitless** (`import_limitless.py`, também via `gerenciar_decks.py limitless ...`):

```
python import_limitless.py list                          # torneios recentes (Regional/Internacional/Mundial)
python import_limitless.py list --types regional international world special
python import_limitless.py import --latest 30            # top 8 dos 30 torneios mais recentes
python import_limitless.py import --ids 581 515          # torneios específicos
python import_limitless.py import --latest 10 --top 16   # top 16
python import_limitless.py online --latest 3             # torneios online (API play.limitlesstcg.com)
```

Opções comuns: `--format standard|standard_jp|expanded`, `--pages`, `--delay` (segundos entre requisições).
Cada deck vira `NN_jogador_arquetipo.txt`; o `index.json` da pasta registra os erros de cada lista.

**Listas suas** (exportadas do TCG Live ou copiadas de um site):

```
python gerenciar_decks.py criar meu_deck --arquivo lista.txt     # ou: ... < lista.txt
python gerenciar_decks.py importar pasta/*.txt                   # vários de uma vez → decks/importados/
```

> A base só conhece o formato **Padrão atual (marcas H/I/J)**. Torneios mais antigos têm cartas já rotacionadas
> e os decks não carregam — use o passo 2.

## 2. Limpar decks fora da rotação

`limpar_decks.py` varre os decks e separa os que têm alguma carta que não existe na base. **Por padrão só simula.**

```
python limpar_decks.py                         # simulação em decks/limitless/ (resumo por torneio)
python limpar_decks.py --detalhes              # mostra as cartas fora da rotação de cada deck
python limpar_decks.py --aplicar               # move para decks/_fora_da_rotacao/limitless/<torneio>/
python limpar_decks.py --aplicar --apagar      # apaga de vez (não recuperável)
python limpar_decks.py decks/limitless/553_regional_sydney     # só uma pasta
python limpar_decks.py --max-fora 2            # tolera até 2 cartas diferentes fora da rotação
```

- O `index.json` do torneio é atualizado; se todos os decks saírem, ele vai junto para a quarentena.
- Para recuperar, mova os arquivos de volta para `decks/limitless/<torneio>/`.
- Com `--max-fora` > 0 sobram decks que **não carregam** no motor (carta desconhecida); só use para inspeção.
- Depois de uma rotação nova (ou ao reconstruir a base de cartas) rode a simulação de novo.

## 3. Alterar

```
python gerenciar_decks.py listar [--pasta limitless]
python gerenciar_decks.py mostrar 01_hedrick_dragapult
python gerenciar_decks.py editar meu_deck --add "1 Boss's Orders" --remove "1 Switch"
python gerenciar_decks.py copiar 01_hedrick_dragapult meu_teste   # copie antes de mexer em deck de torneio
python gerenciar_decks.py exportar meu_deck                       # texto para colar no TCG Live
python gerenciar_decks.py apagar meu_teste                        # vai para decks/_lixeira/
```

`editar` salva mesmo que o total não feche 60 e mostra o relatório de validação; ao adicionar, remova o mesmo
número de cartas. Também dá para editar o `.txt` à mão e validar em seguida.

## 4. Criar

**Montador gráfico** — `python server.py` e abra http://localhost:8765/decks (também há o botão *Montador de decks* no simulador).

- **Esquerda (origem)**, duas abas:
  - *Outro deck*: escolha qualquer deck (meus, importados, torneios, `tests`) e veja as cartas por Pokémon/Treinadores/Energias.
    `+` adiciona 1 cópia (Shift+clique adiciona todas as cópias do deck); *Adicionar tudo* soma o deck inteiro;
    *Duplicar para meus decks* cria a cópia em `decks/meus/` e já a abre à direita.
  - *Buscar cartas*: filtros de categoria iguais às pastas de `cartas/` (Pokémon / Pokémon ex por tipo, Treinadores por
    Apoiadores-Itens-Ferramentas-Estádios, Energias por tipo ou Especiais) e busca por nome em inglês ou português
    (a lista aparece a partir de 3 letras; os filtros se combinam). Cada linha mostra quantas cópias você já tem.
- **Direita (meu deck)**: abra um deck seu ou comece um novo; `+`/`−` ajustam as cópias; o contador mostra `N / 60` e a
  validação do servidor aparece embaixo (cartas com efeito parcial/pendente também). O montador impede mais de 4 cópias por
  nome (exceto Energia Básica) e mais de 1 ACE SPEC.
  - *Salvar alterações* atualiza o deck aberto (só decks de `decks/meus/`); *Salvar como novo* usa o nome digitado e
    recusa nomes que já existem; *Copiar lista* põe o texto no formato do TCG Live na área de transferência.
  - Rascunhos incompletos (≠ 60 cartas) podem ser salvos; os avisos continuam aparecendo.

Pelo terminal:

```
python gerenciar_decks.py montar meu_deck                  # montagem interativa, carta a carta
python gerenciar_decks.py montar meu_deck --base 01_hedrick_dragapult   # partindo de outro deck
python gerenciar_decks.py criar meu_deck --arquivo lista.txt --arquetipo "Dragapult ex"
```

Use `--sobrescrever` para trocar um deck existente. (O botão *Decks…* do simulador continua aceitando uma lista colada em texto.)

## 5. Validar e testar

```
python gerenciar_decks.py validar meu_deck
python gerenciar_decks.py validar --todos
python simulate.py meus/meu_deck tests/01_hedrick_dragapult --games 200
```

Regras checadas: 60 cartas, no máximo 4 cópias por nome (exceto Energia Básica), ao menos 1 Pokémon Básico,
no máximo 1 ACE SPEC, todas as cartas existentes na base. O relatório também lista cartas ainda não 100%
implementadas no motor (`parcial`/`pendente`).

## Fluxo típico

1. `python import_limitless.py import --latest 30`
2. `python limpar_decks.py --aplicar`
3. `python gerenciar_decks.py copiar <deck> meu_deck` → `editar` → `validar`
4. `python simulate.py meus/meu_deck <deck> --games 200`
