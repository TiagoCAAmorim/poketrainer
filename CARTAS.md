# Cartas — explorar e imagens

## Página de cartas

`python server.py` → http://localhost:8765/cartas (a página inicial `/` tem atalhos para tudo).

- **Filtros** (barra à esquerda, combináveis):
  - *Nome* em inglês ou português, a partir de 3 letras; a opção *Buscar também em ataques, Habilidades e texto* amplia a busca.
  - *Implementação no simulador*: Todas · Implementadas · **Com problemas** (parcial + pendente) · Só parciais · Só pendentes.
    O filtro "Com problemas" lista as cartas cujo efeito não está 100% no motor; cada carta mostra um selo
    *parcial*/*pendente* e, ao passar o mouse, a frase que falta implementar.
  - *Categoria / subcategoria* (mesmas pastas de `cartas/`), *tipo*, *estágio* e *coleção*.
  - Link direto: `/cartas?status=problema` abre já filtrada; `/cartas#TWM-130` abre o detalhe da carta.
- **Detalhe** (clique na carta): imagem grande, tipo, PS, fraqueza/resistência/recuo, ataques e Habilidades com
  custo, dano e texto em português e inglês, marcas, regulamento, impressões (coleção e data), outras cartas com
  o mesmo nome e evoluções. Em cada ataque/Habilidade/efeito não implementado aparece a nota do que falta
  (`Problemas de implementação`). `Esc` fecha o detalhe.

## Imagens das cartas

As imagens **não vêm no git**: ficam em `imagens/` (no `.gitignore`). Para baixá-las:

```
python baixar_imagens.py                       # tudo: miniatura (~17 KB) + imagem grande (~75 KB), ~190 MB no total
python baixar_imagens.py --qualidade baixa     # só miniaturas (rápido)
python baixar_imagens.py --nome "Dragapult"    # só cartas cujo nome contém o texto
python baixar_imagens.py --colecao ASC MEG     # só algumas coleções
python baixar_imagens.py --listar-faltantes    # o que ainda não foi baixado
python baixar_imagens.py --refazer             # baixa de novo
python baixar_imagens.py --manual PR-ME-93 pikachu.png   # usa uma imagem salva por você (png/webp/jpg)
```

- Fontes, em ordem: TCGdex (`assets.tcgdex.net`, `.webp`), `images.pokemontcg.io` (`.png`) e, por último,
  `limitlesstcg.com` (`.png`, lida da página da carta em pt ou en; é a única com a 30th Celebration e as promos MEP).
  Cada carta usa a primeira impressão que tiver imagem. As imagens da Limitless são maiores (~60 KB a miniatura, ~140 KB a grande).
- É retomável (pula o que já existe) e educado com o servidor: 4 conexões e uma pequena pausa (`--threads`, `--delay`).
- Estrutura: `imagens/cartas/baixa/<ID>.webp`, `imagens/cartas/alta/<ID>.webp`, `imagens/indice.json` (fonte usada e
  lista `_sem_imagem`). O servidor entrega por `/img/baixa/<ID>` e `/img/alta/<ID>`.
- Sem imagem baixada a página continua funcionando, com um quadro de texto no lugar.
- As imagens são material protegido da The Pokémon Company; use só para estudo/uso pessoal. O PTCG Lab é um projeto pessoal, sem fins lucrativos e sem associação com a The Pokémon Company.
