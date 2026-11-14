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


def _custo(c, x, y, custo, r):
    """Desenha o custo do ataque como círculos com a letra do tipo (sem cor). Devolve o x final."""
    c.setLineWidth(0.5)
    for t in custo:
        c.circle(x + r, y + r * 0.35, r, stroke=1, fill=0)
        c.setFont('Helvetica-Bold', r * 1.35)
        c.drawCentredString(x + r, y + r * 0.35 - r * 0.45, 'C' if t == 'C' else t)
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
    # --- cabeçalho
    y = alt - m - 9
    sub = ''
    if d.kind == 'pokemon':
        est = {0: 'Pokémon Básico', 1: 'Pokémon Fase 1', 2: 'Pokémon Fase 2'}[d.stage]
        tipos = '/'.join(_TIPO_PT.get(t, t) for t in d.types)
        sub = f'{est} · {tipos}' + (f' · evolui de {d.evolves_from}' if d.evolves_from else '')
        hp = f'PS {d.hp}'
    elif d.kind == 'trainer':
        sub, hp = f'Treinador · {_SUB_PT.get(d.subtype, "Treinador")}' + (' · ACE SPEC' if d.ace_spec else ''), ''
    else:
        sub, hp = ('Energia Básica' if d.basic_energy else 'Energia Especial'), ''
    tam = 11.0
    wmax = iw - (c.stringWidth(hp, 'Helvetica-Bold', 9) + 6 if hp else 0)
    while tam > 6 and c.stringWidth(_lat(T['nome']), 'Helvetica-Bold', tam) > wmax:
        tam -= 0.5
    c.setFont('Helvetica-Bold', tam)
    c.drawString(m, y, _lat(T['nome']))
    if hp:
        c.setFont('Helvetica-Bold', 9)
        c.drawRightString(larg - m, y, hp)
    y -= 8
    c.setFont('Helvetica-Oblique', 5.6)
    for ln in _quebrar(c, sub, 'Helvetica-Oblique', 5.6, iw):
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

    def montar(tam):
        linhas, h = [], 0.0
        for tipo, nome, custo, dano, texto in blocos:
            r = tam * 0.62
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
        fr = f'Fraqueza: {d.weakness} ×2' if d.weakness else 'Fraqueza: -'
        rs = f'Resistência: {d.resistance} -{d.resistance_value}' if d.resistance else 'Resistência: -'
        c.drawString(m, base - 10, _lat(fr))
        c.drawCentredString(larg / 2 + 6, base - 10, _lat(rs))
        c.drawRightString(larg - m, base - 10, f'Recuo: {"O" * d.retreat if d.retreat else "-"}')
    c.setFont('Helvetica', 5)
    c.drawString(m, 6.5, _lat(d.id.replace('-', ' ', 1)))
    c.drawRightString(larg - m, 6.5, 'cópia para teste')


def arquivo_imagem(cid: str):
    from .explorer import arquivo_imagem as _ai
    return _ai('alta', cid)


def gerar_pdf(cartas: list, saida=None, *, escala=0.9, papel=PAPEL_PADRAO, simplificado=False, margem=6.0,
              espaco=1.0, orientacao='auto', idioma='pt', guias=True) -> dict:
    """Gera o PDF. `cartas`: ids, um por cópia. `saida`: caminho, ou None para devolver os bytes em `pdf`.
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
                    imgs[cid] = ImageReader(str(f)) if f else None
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
