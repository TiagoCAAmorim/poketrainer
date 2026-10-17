# Biblioteca de cartas — formato TEF–30C (marcas H, I e J)

Todas as cartas legais no formato Padrão atual do Pokémon TCG Live, de *Temporal Forces* (TEF) até
*30th Celebration* (30C), incluindo promos e Energias. Cada carta aparece **uma vez** (reimpressões com o
mesmo efeito ficam listadas em `impressoes`). Textos em inglês (oficial) e em português.

## Onde está cada coisa

| Arquivo / pasta | Conteúdo |
|---|---|
| `cartas.db` | Banco SQLite com tudo (tabelas `cartas`, `ataques`, `habilidades`, `impressoes`, `colecoes`, busca de texto `busca`). Aguenta qualquer volume e abre em qualquer leitor de SQLite (DB Browser for SQLite, Python, Excel via ODBC). |
| `Treinadores.json` | Todos os Treinadores, agrupados por pasta |
| `Pokemon.json` | Todos os Pokémon, agrupados por pasta |
| `Energias.json` | Todas as Energias, agrupadas por pasta |
| `Treinadores/Apoiadores`, `Itens`, `Ferramentas`, `Estadios` | 1 arquivo JSON por carta |
| `Pokemon/Pokemon_EX/<Tipo>` | Pokémon ex (inclui Mega Evolução ex), separados por tipo |
| `Pokemon/<Tipo>` | demais Pokémon: Planta, Fogo, Agua, Eletrico, Psiquico, Lutador, Escuridao, Metal, Dragao, Incolor |
| `Energias/<Tipo>` | Energias básicas de cada tipo |
| `Energias/Especiais` | Energias Especiais |
| `_indice.md` (em cada pasta) | tabela legível: carta, nome em português, ID e **o que a carta faz** |

## Campos de cada carta (JSON)

`id` (código da impressão principal, ex. `TWM-130`), `nome`, `nome_pt`, `categoria`, `tipo`, `hp`, `estagio`,
`evolui_de`, `pokemon_ex`, `mega`, `tera`, `fraqueza`, `resistencia`, `recuo`, `premios_ao_ser_nocauteado`,
`habilidades` / `ataques` (nome, nome_pt, custo, dano, texto, texto_pt), `subtipo` e `texto`/`texto_pt`
(Treinadores e Energias), `regras` (ex, Tera, ACE SPEC, Apoiador…), `regulamento`, `impressoes`
(código, coleção, data) e `simulador` (se o efeito já está implementado no motor e o que falta).

## Consultar

```
python cartas.py buscar "contadores de dano"       # busca em português ou inglês
python cartas.py mostrar TWM-130                    # ficha completa
python cartas.py listar --categoria Treinador --subtipo Apoiador
python cartas.py listar --categoria Pokémon --tipo Fogo --ex
python cartas.py resumo
```

SQL direto, por exemplo: `SELECT nome, nome_pt, hp FROM v_pokemon WHERE tipo='Psíquico' AND pokemon_ex=1;`

## Atualizar

Quando sair coleção nova: `python tools/build_carddb.py && python tools/build_pt_texts.py && python cartas.py atualizar`.
