"""Gera PDFs com um conjunto de cartas para imprimir (proxy / playtest), em escala configurável.

- tamanho real de uma carta: 63 × 88 mm; `escala` (0,9 = 90%) multiplica as duas medidas;
- cartas repetidas aparecem repetidas (uma por cópia);
- `simplificado=True` desenha cada carta só com texto, em preto e branco (sem arte, economiza tinta);
  no modo normal usa as imagens de `imagens/cartas/alta` (python baixar_imagens.py) e cai para a versão
  simplificada nas cartas sem imagem (a lista volta em `faltando`);
- papel: A4 (padrão), Office (Ofício 216 × 330 mm), A5, Letter, Legal, A3 ou "LARGURAxALTURA" em mm.
  A orientação (retrato/paisagem) que couber mais cartas por página é escolhida automaticamente.
"""
from __future__ import annotations

import math
import io
import json
import re
from collections import Counter
from pathlib import Path

from .carddb import db

CARTA_MM = (63.0, 88.0)
PT = 72 / 25.4   # pontos por mm
PAPEIS = {'A4': (210.0, 297.0), 'Office': (216.0, 330.0), 'A5': (148.0, 210.0), 'Letter': (215.9, 279.4),
          'Legal': (215.9, 355.6), 'A3': (297.0, 420.0)}
PAPEL_PADRAO = 'A4'
ROTULO_PAPEL = {'A4': 'A4 (210 × 297 mm)', 'Office': 'Office / Ofício (216 × 330 mm)', 'A5': 'A5 (148 × 210 mm)',
                'Letter': 'Letter (216 × 279 mm)', 'Legal': 'Legal (216 × 356 mm)', 'A3': 'A3 (297 × 420 mm)'}
ESCALA_MIN, ESCALA_MAX = 20, 150   # % do tamanho real
_PT_JSON = Path(__file__).resolve().parent / 'data' / 'cards_pt.json'
_pt_cache: dict | None = None
_TIPO_PT = {'G': 'Planta', 'R': 'Fogo', 'W': 'Água', 'L': 'Elétrico', 'P': 'Psíquico', 'F': 'Lutador',
            'D': 'Escuridão', 'M': 'Metal', 'N': 'Dragão', 'C': 'Incolor', 'Y': 'Fada'}
_CAT_PT = {'supporter': 'APOIADOR', 'item': 'ITEM', 'tool': 'FERRAMENTA', 'stadium': 'ESTÁDIO'}
_SUB_PT = {'supporter': 'Apoiador', 'item': 'Item', 'tool': 'Ferramenta Pokémon', 'stadium': 'Estádio'}


# ------------------------------------------------------------------ papel e layout
def papeis() -> list:
    return [{'id': k, 'label': ROTULO_PAPEL[k], 'mm': list(PAPEIS[k])} for k in PAPEIS]


def tamanho_papel(papel) -> tuple:
    """(largura, altura) em mm, em retrato. Aceita nome (sem distinguir maiúsculas), 'LxA' em mm ou tupla."""
    if isinstance(papel, (tuple, list)):
        w, h = float(papel[0]), float(papel[1])
    else:
        s = str(papel or PAPEL_PADRAO).strip()
        achado = next((k for k in PAPEIS if k.lower() == s.lower()), None)
        if achado is None and s.lower() in ('ofício', 'oficio'):
            achado = 'Office'
        if achado:
            w, h = PAPEIS[achado]
        else:
            m = re.match(r'^(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?:\s*mm)?$', s, re.I)
            if not m:
                raise ValueError(f'Papel desconhecido: {papel!r} (use {", ".join(PAPEIS)} ou LARGURAxALTURA em mm)')
            w, h = float(m.group(1).replace(',', '.')), float(m.group(2).replace(',', '.'))
    if min(w, h) < 40:
        raise ValueError('Papel pequeno demais.')
    return (min(w, h), max(w, h))


def layout(papel=PAPEL_PADRAO, escala=0.9, margem=6.0, espaco=1.0, orientacao='auto') -> dict:
    """Grade de cartas por página. Medidas em mm; `orientacao`: auto | retrato | paisagem."""
    if not (ESCALA_MIN / 100 <= escala <= ESCALA_MAX / 100):
        raise ValueError(f'Escala deve ficar entre {ESCALA_MIN}% e {ESCALA_MAX}%.')
    pw, ph = tamanho_papel(papel)
    cw, ch = CARTA_MM[0] * escala, CARTA_MM[1] * escala
    melhor = None
    for nome, (W, H) in (('retrato', (pw, ph)), ('paisagem', (ph, pw))):
        if orientacao not in ('auto', nome):
            continue
        cols = int((W - 2 * margem + espaco + 1e-6) // (cw + espaco))
        lins = int((H - 2 * margem + espaco + 1e-6) // (ch + espaco))
        if cols > 0 and lins > 0 and (melhor is None or cols * lins > melhor['cols'] * melhor['lins']):
            melhor = {'orientacao': nome, 'W': W, 'H': H, 'cols': cols, 'lins': lins}
    if melhor is None:
        raise ValueError('A carta nesta escala não cabe no papel com essa margem (reduza a escala ou a margem).')
    melhor.update(por_pagina=melhor['cols'] * melhor['lins'], cw=cw, ch=ch, margem=margem, espaco=espaco)
    return melhor


# ------------------------------------------------------------------ conjunto de cartas
def _pt() -> dict:
    global _pt_cache
    if _pt_cache is None:
        _pt_cache = json.load(open(_PT_JSON, encoding='utf-8')) if _PT_JSON.exists() else {}
    return _pt_cache


def expandir(itens) -> list:
    """[{id, n}] ou {id: n} → lista de ids (uma por cópia), agrupando cópias e ordenando Pokémon, Treinadores, Energias."""
    D = db()
    cont: Counter = Counter()
    pares = itens.items() if isinstance(itens, dict) else [(i['id'], i['n']) for i in itens]
    for cid, n in pares:
        if cid not in D.cards:
            raise ValueError(f'Carta desconhecida: {cid}')
        cont[cid] += max(0, int(n))
    ordem = {'pokemon': 0, 'trainer': 1, 'energy': 2}
    ids = sorted((c for c in cont if cont[c] > 0), key=lambda c: (ordem[D.cards[c].kind], D.cards[c].name, c))
    return [c for c in ids for _ in range(cont[c])]


def ajustar(cartas: list, adicionar: list = (), remover: list = ()) -> list:
    """Aplica textos '2 Boss's Orders' / '1 Dragapult ex TWM 130' (formato de lista de deck) a uma lista de ids."""
    from .decks import parse_decklist
    cont = Counter(cartas)
    for textos, sinal in ((adicionar, 1), (remover, -1)):
        for t in textos:
            t = t.strip()
            if not re.match(r'^\d', t):
                t = '1 ' + t
            deck, erros = parse_decklist(t)
            if erros:
                raise ValueError('; '.join(erros))
            for cid, n in Counter(deck.cards).items():
                cont[cid] += sinal * n
    return [c for c in expandir(cont)]


# ------------------------------------------------------------------ desenho
def _lat(s: str) -> str:
    """Troca caracteres fora do Latin-1/WinAnsi (fontes padrão do PDF) por equivalentes."""
    s = (s or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
    s = s.replace('•', '*').replace('→', '->').replace('♀', '(F)').replace('♂', '(M)').replace('\n', ' ')
    return s.encode('cp1252', 'replace').decode('cp1252')


def _quebrar(c, texto, fonte, tam, largura):
    from reportlab.lib.utils import simpleSplit
    return simpleSplit(_lat(texto), fonte, tam, largura) if texto else []


def _textos(d, idioma):
    """Nome, e textos (carta, habilidades, ataques) no idioma pedido, com queda para o inglês."""
    pt = _pt().get(d.id) or {} if idioma == 'pt' else {}
    nome_pt = pt.get('name') or d.name_pt or ''
    ab = [(a.name, a.text) for a in d.abilities]
    at = [(a.name, a.text) for a in d.attacks]
    for lista, chave in ((ab, 'abilities'), (at, 'attacks')):
        for i, x in enumerate(pt.get(chave) or []):
            if i < len(lista):
                lista[i] = (x.get('name') or lista[i][0], x.get('text') or lista[i][1])
    return {'nome': d.name, 'nome_pt': nome_pt if nome_pt and nome_pt != d.name else '',
            'texto': pt.get('text') or d.text, 'abilities': ab, 'attacks': at}


def _estrela(n, ri):
    return [((ri if i % 2 else 1) * math.cos(math.pi / 2 + i * math.pi / n),
             (ri if i % 2 else 1) * math.sin(math.pi / 2 + i * math.pi / n)) for i in range(2 * n)]


def _lente(a, b, n, larg, vert=1.0):
    """Forma de folha/olho entre os pontos a e b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy)
    nx, ny = -dy / ln, dx / ln

    def lado(sg):
        r = []
        for i in range(n + 1):
            t = i / n
            w = sg * larg * math.sin(math.pi * t) ** vert
            r.append((a[0] + dx * t + nx * w, a[1] + dy * t + ny * w))
        return r
    return lado(1) + lado(-1)[::-1][1:-1]


# Glifos em coordenadas -1..1 (y para cima), iguais aos de site/pdf.js. g: f=preenche, s=contorno, c=disco preto,
# b=disco branco, bp=polígono branco, bl=linha branca.
_GLIFOS = {
    'R': lambda g: (g.f([(0.1, 1), (0.55, 0.3), (0.8, -0.25), (0.5, -0.85), (0, -1), (-0.5, -0.85), (-0.8, -0.25),
                         (-0.45, 0.2), (-0.25, -0.15), (-0.2, 0.45)]), g.b(0, -0.5, 0.28)),
    'W': lambda g: (g.f([(0, 1), (-0.6, -0.05), (0.6, -0.05)]), g.c(0, -0.35, 0.65)),
    'L': lambda g: g.f([(0.25, 1), (-0.55, -0.1), (-0.05, -0.1), (-0.25, -1), (0.55, 0.15), (0.05, 0.15)]),
    'G': lambda g: (g.f(_lente((-0.8, -0.8), (0.8, 0.8), 10, 0.55, 0.8)), g.bl((-0.95, -0.95), (0.55, 0.55))),
    'P': lambda g: (g.s(_lente((-1, 0), (1, 0), 12, 0.6, 0.9)), g.c(0, 0, 0.3)),
    'F': lambda g: (g.f([(-0.8, -0.5), (-0.5, 0.5), (0.1, 0.85), (0.8, 0.3), (0.7, -0.6), (0, -0.85)]),
                    g.bl((-0.2, 0.5), (0.05, -0.1)), g.bl((0.05, -0.1), (0.45, -0.25))),
    'D': lambda g: (g.c(0, 0, 0.85), g.b(0.42, 0.28, 0.72)),
    'M': lambda g: (g.f(_estrela(6, 0.87)), g.b(0, 0, 0.34)),
    'N': lambda g: (g.f([(0, 1), (0.7, 0), (0, -1), (-0.7, 0)]), g.bp([(0, 0.5), (0.3, 0), (0, -0.5), (-0.3, 0)])),
    'C': lambda g: g.f(_estrela(5, 0.42)),
    'Y': lambda g: g.f(_estrela(4, 0.27)),
}


def _icone(c, t, x, y, R):
    """Ícone do tipo `t` (círculo com glifo, só preto e branco) com centro (x, y) e raio R."""
    u = R * 0.72

    def pts(ps):
        return [(x + a * u, y + b * u) for a, b in ps]

    def poly(ps, fill, stroke):
        p = c.beginPath()
        q = pts(ps)
        p.moveTo(*q[0])
        for pt in q[1:]:
            p.lineTo(*pt)
        p.close()
        c.drawPath(p, fill=fill, stroke=stroke)

    def cor(v):
        c.setFillColorRGB(v, v, v)
        c.setStrokeColorRGB(v, v, v)

    class G:
        @staticmethod
        def f(ps):
            cor(0); poly(ps, 1, 0)

        @staticmethod
        def s(ps):
            cor(0); c.setLineWidth(max(0.5, R * 0.13)); poly(ps, 0, 1)

        @staticmethod
        def c(a, b, r):
            cor(0); c.circle(x + a * u, y + b * u, r * u, stroke=0, fill=1)

        @staticmethod
        def b(a, b, r):
            cor(1); c.circle(x + a * u, y + b * u, r * u, stroke=0, fill=1); cor(0)

        @staticmethod
        def bp(ps):
            cor(1); poly(ps, 1, 0); cor(0)

        @staticmethod
        def bl(p1, p2):
            cor(1); c.setLineWidth(max(0.5, R * 0.1))
            c.line(x + p1[0] * u, y + p1[1] * u, x + p2[0] * u, y + p2[1] * u); cor(0)

    c.saveState()
    cor(0)
    c.setLineWidth(max(0.4, R * 0.09))
    c.circle(x, y, R, stroke=1, fill=0)
    _GLIFOS.get(t, _GLIFOS['C'])(G)
    c.restoreState()


def _custo(c, x, y, custo, r):
    """Desenha o custo do ataque como ícones de tipo (sem cor). Devolve o x final."""
    for t in custo:
        _icone(c, t, x + r, y + r * 0.35, r)
        x += 2 * r + 1.2
    return x


def carta_simplificada(c, d, idioma='pt', larg=CARTA_MM[0] * PT, alt=CARTA_MM[1] * PT):
    """Desenha a carta em (0,0)-(larg,alt), só texto e linhas pretas."""
    T = _textos(d, idioma)
    m = 7.0
    iw = larg - 2 * m
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(1.2)
    c.roundRect(0.6, 0.6, larg - 1.2, alt - 1.2, 8, stroke=1, fill=0)
    c.setLineWidth(0.4)
    c.roundRect(4, 4, larg - 8, alt - 8, 5, stroke=1, fill=0)
    # --- cabeçalho: nome, ícone(s) de tipo e PS; depois [CATEGORIA] e subtítulo
    y = alt - m - 9
    tag, sub, hp = '', '', ''
    if d.kind == 'pokemon':
        tag = 'POKÉMON'
        sub = {0: 'Básico', 1: 'Fase 1', 2: 'Fase 2'}[d.stage] + (f' · evolui de {d.evolves_from}' if d.evolves_from else '')
        hp = f'PS {d.hp}'
    elif d.kind == 'trainer':
        tag = _CAT_PT.get(d.subtype, 'TREINADOR')
        sub = 'ACE SPEC' if d.ace_spec else ''
    else:
        tag, sub = 'ENERGIA', ('Básica' if d.basic_energy else 'Especial')
    R = 5.2
    tipos = list(d.types) if d.kind == 'pokemon' else []
    w_ic = len(tipos) * (2 * R + 1.5)
    w_hp = c.stringWidth(hp, 'Helvetica-Bold', 9) + 5 if hp else 0
    tam = 11.0
    wmax = iw - w_hp - w_ic - 2
    while tam > 6 and c.stringWidth(_lat(T['nome']), 'Helvetica-Bold', tam) > wmax:
        tam -= 0.5
    c.setFont('Helvetica-Bold', tam)
    c.drawString(m, y, _lat(T['nome']))
    if hp:
        c.setFont('Helvetica-Bold', 9)
        c.drawRightString(larg - m, y, hp)
    for i, t in enumerate(tipos):
        _icone(c, t, larg - m - w_hp - R - i * (2 * R + 1.5) - 1, y + 3.1, R)
    y -= 9.6
    c.setFont('Helvetica-Bold', 5.8)
    wt = c.stringWidth(_lat(tag), 'Helvetica-Bold', 5.8) + 5
    c.setLineWidth(0.5)
    c.rect(m, y - 1.7, wt, 7.4, stroke=1, fill=0)
    c.drawString(m + 2.5, y, _lat(tag))
    c.setFont('Helvetica-Oblique', 5.8)
    ls = _quebrar(c, sub, 'Helvetica-Oblique', 5.8, iw - wt - 4)
    if ls:
        c.drawString(m + wt + 4, y, ls[0])
    y -= 6.6
    for ln in ls[1:]:
        c.drawString(m, y, ln)
        y -= 6.4
    if T['nome_pt']:
        c.setFont('Helvetica', 5.8)
        c.drawString(m, y, _lat(f'({T["nome_pt"]})'))
        y -= 6.4
    y -= 1.5
    c.setLineWidth(0.5)
    c.line(m, y, larg - m, y)
    topo, base = y - 4, 22.0   # área do corpo; rodapé abaixo de `base`
    # --- corpo: blocos (tipo, título, custo, dano, texto)
    blocos = []
    if d.kind == 'pokemon':
        for n, t in T['abilities']:
            blocos.append(('hab', n, [], '', t))
        for (n, t), a in zip(T['attacks'], d.attacks):
            blocos.append(('atq', n, list(a.cost), a.damage_label, t))
    elif T['texto']:
        blocos.append(('txt', '', [], '', T['texto']))
    if d.kind == 'energy' and not T['texto']:
        blocos.append(('txt', '', [], '', f'Fornece Energia de {_TIPO_PT.get(d.provides, d.provides)}.'))
    if d.kind == 'pokemon' and T['texto']:
        blocos.append(('txt', '', [], '', T['texto']))

    if d.kind == 'energy' and d.basic_energy and d.provides:
        _icone(c, d.provides, larg / 2, base + (topo - base) * 0.62, 24)

    def montar(tam):
        linhas, h = [], 0.0
        for tipo, nome, custo, dano, texto in blocos:
            r = tam * 0.7
            ltxt = _quebrar(c, texto, 'Helvetica', tam, iw)
            h += (tam * 1.35 if tipo != 'txt' else 0) + len(ltxt) * tam * 1.2 + tam * 0.9
            linhas.append((tipo, nome, custo, dano, ltxt, r))
        return linhas, h
    tam = 8.2
    while True:
        linhas, h = montar(tam)
        if h <= topo - base or tam <= 4.2:
            break
        tam -= 0.2
    yy = topo
    for tipo, nome, custo, dano, ltxt, r in linhas:
        if tipo != 'txt':
            yy -= tam * 1.1
            x = m
            if tipo == 'hab':
                c.setFont('Helvetica-Bold', tam)
                c.setLineWidth(0.5)
                c.rect(x, yy - 1, c.stringWidth('HAB', 'Helvetica-Bold', tam) + 4, tam + 1.5, stroke=1, fill=0)
                c.drawString(x + 2, yy, 'HAB')
                x += c.stringWidth('HAB', 'Helvetica-Bold', tam) + 8
            else:
                x = _custo(c, x, yy - 0.5, custo, r) + 2
            c.setFont('Helvetica-Bold', tam + 0.6)
            c.drawString(x, yy, _lat(nome))
            if dano:
                c.drawRightString(larg - m, yy, _lat(dano))
            yy -= tam * 0.25
        c.setFont('Helvetica', tam)
        for ln in ltxt:
            yy -= tam * 1.2
            c.drawString(m, yy, ln)
        yy -= tam * 0.9
    # --- rodapé
    c.setLineWidth(0.5)
    c.line(m, base - 2, larg - m, base - 2)
    c.setFont('Helvetica', 6)
    if d.kind == 'pokemon':
        r, yb = 3.5, base - 10

        def txt(x, t):
            c.setFont('Helvetica', 6)
            c.drawString(x, yb, _lat(t))
            return x + c.stringWidth(_lat(t), 'Helvetica', 6)

        def grupo(x0, rot, tp, suf):   # "Fraqueza: [ícone] ×2"
            x = txt(x0, rot + ':') + 2
            if tp:
                _icone(c, tp, x + r, yb + 2, r)
                txt(x + 2 * r + 2, suf)
            else:
                txt(x, '-')
        grupo(m, 'Fraqueza', d.weakness, '×2')
        w_res = c.stringWidth('Resistência:', 'Helvetica', 6) + 2 + (
            2 * r + 2 + c.stringWidth(_lat(f'-{d.resistance_value}'), 'Helvetica', 6) if d.resistance else 4)
        grupo(larg / 2 + 4 - w_res / 2, 'Resistência', d.resistance, f'-{d.resistance_value}' if d.resistance else '')
        nr = d.retreat or 0
        w_rec = c.stringWidth('Recuo:', 'Helvetica', 6) + 2 + (nr * (2 * r + 1.2) if nr else 4)
        x = txt(larg - m - w_rec, 'Recuo:') + 2
        if nr:
            for _ in range(nr):
                _icone(c, 'C', x + r, yb + 2, r)
                x += 2 * r + 1.2
        else:
            txt(x, '-')
    c.setFont('Helvetica', 5)
    c.drawString(m, 6.5, _lat(d.id.replace('-', ' ', 1)))
    c.drawRightString(larg - m, 6.5, 'cópia para teste')


def arquivo_imagem(cid: str):
    from .explorer import arquivo_imagem as _ai
    return _ai('alta', cid)


def imagem_economica(origem, forca=1.0):
    """Versão econômica da arte da carta: escala de cinza, sem fundos coloridos, só os traços (texto, molduras, contornos
    da ilustração) em tons de cinza sobre papel branco. Mantém a diagramação original. `origem`: caminho ou imagem PIL."""
    import numpy as np
    from PIL import Image, ImageFilter
    im = origem if hasattr(origem, 'convert') else Image.open(origem)
    im = im.convert('RGBA')
    papel = Image.new('RGBA', im.size, (255, 255, 255, 255))
    papel.alpha_composite(im)
    g = papel.convert('L')
    a = np.asarray(g, dtype=np.float32)
    fundo = np.asarray(g.filter(ImageFilter.GaussianBlur(im.size[0] * 0.008)), dtype=np.float32)   # tom local
    d = a - fundo
    # em regiões escuras o texto/traço é mais CLARO que o fundo (ex.: texto branco sobre azul-escuro); nas claras, mais escuro
    w = np.clip((fundo - 90) / 40, 0, 1)
    tinta = w * np.where(d < 0, -d, 0.8 * d) + (1 - w) * np.where(d > 0, d, -0.35 * d)
    tinta = np.clip((tinta - 7) * 3.2 / 255 * forca, 0, 1)
    return Image.fromarray((255 * (1 - 0.9 * tinta)).astype(np.uint8), 'L')


def gerar_pdf(cartas: list, saida=None, *, escala=0.9, papel=PAPEL_PADRAO, simplificado=False, margem=6.0,
              espaco=1.0, orientacao='auto', idioma='pt', guias=True, economico=False) -> dict:
    """Gera o PDF. `cartas`: ids, um por cópia. `saida`: caminho, ou None para devolver os bytes em `pdf`.
    `economico`: usa a arte original em cinza, sem fundos coloridos (menos tinta; `imagem_economica`).
    Retorna {pdf, paginas, cartas, por_pagina, orientacao, faltando(ids sem imagem desenhados simplificados), ...}."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    D = db()
    if not cartas:
        raise ValueError('Nenhuma carta para imprimir.')
    for cid in cartas:
        if cid not in D.cards:
            raise ValueError(f'Carta desconhecida: {cid}')
    L = layout(papel, escala, margem, espaco, orientacao)
    buf = io.BytesIO() if saida is None else None
    c = canvas.Canvas(buf if buf is not None else str(saida), pagesize=(L['W'] * PT, L['H'] * PT))
    c.setTitle('Cartas para impressão')
    c.setAuthor('PTCG Lab')
    cw, ch, gap = L['cw'] * PT, L['ch'] * PT, espaco * PT
    gx = (L['W'] * PT - (L['cols'] * cw + (L['cols'] - 1) * gap)) / 2
    gy = (L['H'] * PT - (L['lins'] * ch + (L['lins'] - 1) * gap)) / 2
    base_w, base_h = CARTA_MM[0] * PT, CARTA_MM[1] * PT
    imgs, faltando = {}, []
    paginas = 0
    for i, cid in enumerate(cartas):
        pos = i % L['por_pagina']
        if pos == 0 and i:
            c.showPage()
        if pos == 0:
            paginas += 1
        col, lin = pos % L['cols'], pos // L['cols']
        x = gx + col * (cw + gap)
        y = L['H'] * PT - gy - (lin + 1) * ch - lin * gap
        d = D.cards[cid]
        img = None
        if not simplificado:
            if cid not in imgs:
                f = arquivo_imagem(cid)
                try:
                    imgs[cid] = (ImageReader(imagem_economica(f)) if economico else ImageReader(str(f))) if f else None
                except Exception:   # imagem corrompida
                    imgs[cid] = None
            img = imgs[cid]
            if img is None and cid not in faltando:
                faltando.append(cid)
        c.saveState()
        c.translate(x, y)
        if img is not None:
            c.drawImage(img, 0, 0, cw, ch)
            if guias:
                c.setStrokeColorRGB(.6, .6, .6)
                c.setLineWidth(0.25)
                c.rect(0, 0, cw, ch, stroke=1, fill=0)
        else:
            c.scale(cw / base_w, ch / base_h)
            carta_simplificada(c, d, idioma, base_w, base_h)
        c.restoreState()
    c.showPage()
    c.save()
    return {'pdf': buf.getvalue() if buf is not None else None, 'arquivo': str(saida) if saida else None,
            'paginas': paginas, 'cartas': len(cartas), 'por_pagina': L['por_pagina'], 'orientacao': L['orientacao'],
            'colunas': L['cols'], 'linhas': L['lins'], 'tamanho_carta_mm': [round(L['cw'], 1), round(L['ch'], 1)],
            'faltando': [f'{D.cards[f].name} ({f})' for f in faltando]}
