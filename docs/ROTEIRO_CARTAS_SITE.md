# Roteiro — atualizar as cartas da página estática

Os **decks** da página são atualizados sozinhos toda segunda-feira (`.github/workflows/decks-semanal.yml`).
As **cartas** (`site/data/cartas.js`) são atualizadas **à mão**, quando sai coleção nova (quase todo mês), quando há
errata/tradução nova ou quando o workflow dos decks falha por "carta não encontrada".
Este roteiro serve para uma pessoa ou para uma IA (Claude Code) conduzir e avaliar a atualização.

## 1. Quando rodar
- Saiu coleção nova ou promo (a Limitless já mostra decks com cartas dela), ou
- o workflow "Atualizar decks da temporada" falhou em `tests/test_site.py` com carta de deck não encontrada, ou
- começou uma temporada nova (rotação): ver o passo 5.

## 2. Rodar
```
git checkout main && git pull
git checkout -b site-cartas-AAAA-MM
python tools/atualizar_cartas_site.py          # reconstrói a base, regera site/data e escreve .cache/relatorio_cartas_site.md
python tools/baixar_temporada.py               # só se quiser decks novos já agora (o workflow semanal também faz)
python tools/build_site.py --so-decks          # regera decks.js com a base nova
python tests/test_site.py
```
`--sem-rede` reaproveita as fontes já baixadas em `.cache/`.

## 3. O que conferir no relatório (`.cache/relatorio_cartas_site.md`)
| Item | Normal | Investigar se… |
|---|---|---|
| Cartas novas | só as da coleção nova (+ promos) | vieram milhares: a marca ou o filtro mudou |
| **Sumiram** | nenhuma | qualquer uma: uma marca saiu de `MARCAS`, a fonte mudou o id, ou a carta foi renomeada |
| Alteradas | poucas (errata, texto corrigido) | muitas: mudou o formato do texto na fonte (símbolos, espaços) |
| Coleções novas | as esperadas | código estranho (ex.: promo sem número) |
| Sem tradução | ≈ 429 hoje (inclui Pokémon sem texto algum); só deve crescer com as coleções novas | salto grande: o TCGdex ainda não traduziu; a página cai para o inglês, aceitável por um tempo |
| `tests/test_site.py` | OK | FALHOU: carta de deck não resolvida → ver passo 4 |

Confira também a olho:
1. `python -m http.server -d site` e abra a página: carregue um deck do torneio mais novo e gere o PDF em EN e PT.
2. Procure uma carta nova na busca (inglês e português) e veja se o texto cabe na carta do PDF.
3. `git diff --stat site/data` — o tamanho de `cartas.js` não deve crescer fora do esperado (hoje ≈ 1,6 MB).

## 4. Se um deck tem carta desconhecida
`build_site.py` lista as cartas ("fora da base"). Causas comuns, em ordem:
1. Coleção ainda não está nas fontes (pokemon-tcg-data / TCGdex): espere e rode de novo.
2. Marca de regulação fora de `MARCAS` em `tools/atualizar_cartas_site.py`: acrescente e rode de novo.
3. Nome diferente entre Limitless e a base (acento, apóstrofo, "Basic X Energy"): `resolver` em `tools/build_site.py` e
   `resolver` em `site/app.js` tentam por SET+NUM e depois pelo nome; ajuste o alias se for um padrão novo.

## 5. Temporada nova (rotação, em set/ago)
- `python tools/baixar_temporada.py` já cria `ptcg/data/temporada_AAAA.json` sozinho (AAAA = ano em que a temporada termina).
- `MARCAS`: cartas da marca que saiu de rotação só precisam ficar enquanto houver decks que as usem (as temporadas antigas
  continuam na página). Se quiser reduzir o tamanho, apague as temporadas antigas **e** a marca.
- O rótulo "(atual)" no seletor é sempre a temporada mais recente.

## 6. Fechar
```
git add site/data ptcg/data
git commit -m "Site: cartas até <coleção>"
git push -u origin site-cartas-AAAA-MM   # e abra o PR; depois do merge o Pages publica sozinho
```
Se a mudança também serve ao motor (coleção nova), a base do motor segue o fluxo do CLAUDE.md
(`build_carddb.py`, `build_pt_texts.py`, `cartas.py atualizar`): é independente da do site.

## 7. Instruções para a IA que for conduzir
- Rode os comandos do passo 2, leia o relatório e os avisos do `build_carddb`/`build_pt_texts`.
- Aplique a tabela do passo 3 e **pare para perguntar** se algo "sumiu", se houver mais de ~300 cartas alteradas ou se o
  teste falhar por motivo que você não entende; não edite `site/data/*.js` à mão (são gerados).
- Não mexa na base do motor (`ptcg/data/cards*.json`) neste fluxo.
- Entregue: resumo do relatório, o que foi verificado na página e o link do PR.
