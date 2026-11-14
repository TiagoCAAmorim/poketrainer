# Página estática — PDF de cartas simplificadas

Página sem servidor: HTML + JS puro. Gera no navegador o mesmo PDF "simplificado" (só texto, preto e branco)
de `ptcg/imprimir.py`, em inglês ou português, com a lista de cartas vinda de um deck da temporada, de uma lista colada
ou da busca com sugestões.

- Abrir: dê duplo clique em `site/index.html` (funciona sem servidor) ou sirva a pasta (`python -m http.server -d site`).
- Publicar: qualquer hospedagem estática serve (ex.: GitHub Pages apontando para a pasta `site/`).
- **Chave Pix**: edite `PIX_KEY` no topo de `app.js` (vazio esconde o convite do café).

## Arquivos
| Arquivo | O que é |
|---|---|
| `index.html`, `style.css`, `app.js` | interface, busca com sugestões, importação, textos EN/PT |
| `pdf.js` | desenho da carta e do layout; port de `carta_simplificada`/`layout` de `ptcg/imprimir.py` |
| `vendor/jspdf.umd.min.js` | jsPDF 2.5.2 (MIT), versionado para a página funcionar offline |
| `data/cartas.js`, `data/decks.js` | **gerados** — não editar à mão |

## Atualizar os dados
A página usa uma base própria (marcas G, H, I, J) porque os decks da temporada ainda têm cartas da marca G; a base do motor (H, I, J) não muda.
```
python tools/build_carddb.py --marks G,H,I,J --out .cache/cards_site.json          # base do site (inclui a marca G)
python tools/build_pt_texts.py --cards .cache/cards_site.json --out .cache/cards_pt_site.json
python tools/baixar_temporada.py     # top 16 de cada Regional/Internacional/Mundial da temporada → ptcg/data/temporada_2026.json
python tools/build_site.py           # cartas + decks → site/data/*.js
python tests/test_site.py
```
Ao mudar `carta_simplificada` em Python, mude também `pdf.js` (os dois devem produzir o mesmo desenho).
