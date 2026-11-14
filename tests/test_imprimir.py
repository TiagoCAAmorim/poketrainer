"""Testes do PDF de cartas (ptcg/imprimir.py): escala, papel, cópias repetidas, cartas simplificadas e imagens."""
import os
import re
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg import imprimir as IMP  # noqa: E402
from ptcg.decks import load_deck  # noqa: E402


def _paginas(pdf: bytes) -> int:
    return len(re.findall(rb'/Type\s*/Page\b(?!s)', pdf))


def test_layout_e_papel():
    L = IMP.layout('A5', 0.9)
    assert (round(L['cw'], 1), round(L['ch'], 1)) == (56.7, 79.2) and L['por_pagina'] == 4   # 90% em A5: 2×2
    assert IMP.layout('a5', 1.0)['por_pagina'] == 4 and IMP.layout('A5', 1.1)['por_pagina'] < 4   # 100%: ainda 2×2
    assert IMP.layout('Office', 0.9)['por_pagina'] >= 9 and IMP.tamanho_papel('Office') == (216.0, 330.0)
    assert IMP.tamanho_papel('300x200') == (200.0, 300.0)                                    # sempre retrato
    assert IMP.layout('A4', 0.9)['por_pagina'] == 9
    assert IMP.layout('A4', 0.9, orientacao='paisagem')['orientacao'] == 'paisagem'
    for ruim in (lambda: IMP.tamanho_papel('A99'), lambda: IMP.layout('A5', 5), lambda: IMP.layout('A5', 1.0, margem=60)):
        try:
            ruim()
        except ValueError:
            continue
        raise AssertionError('deveria recusar')
    assert IMP.PAPEL_PADRAO == 'A4' and IMP.papeis()[0]['id'] == 'A4' and IMP.papeis()[1]['id'] == 'Office'               # ordem pedida


def test_conjunto_e_ajuste():
    ids = load_deck('tests/01_hedrick_dragapult').cards
    cont = Counter(ids)
    base = IMP.expandir(cont)
    assert len(base) == 60 and Counter(base) == cont                                          # repetidas ficam repetidas
    novo = IMP.ajustar(base, ["2 Ultra Ball"], ["1 Boss's Orders"])
    assert len(novo) == 61
    assert Counter(novo)['MEG-114'] == cont['MEG-114'] - 1
    assert Counter(novo)['MEG-131'] == cont['MEG-131'] + 2                                   # Ultra Ball
    assert len(IMP.ajustar(base, [], ['99 Ultra Ball'])) == 60 - cont['MEG-131']                               # não gera cópias negativas


def test_pdf_simplificado():
    ids = IMP.expandir(Counter(load_deck('tests/01_hedrick_dragapult').cards))
    r = IMP.gerar_pdf(ids, simplificado=True, papel='A5')
    assert r['por_pagina'] == 4 and r['paginas'] == 15 and r['pdf'].startswith(b'%PDF')
    assert _paginas(r['pdf']) == 15 and not r['faltando']
    r = IMP.gerar_pdf(ids[:10], papel='Office', escala=0.9, simplificado=True, idioma='en')
    assert r['paginas'] == 1
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'x.pdf')
        IMP.gerar_pdf(ids[:3], out, simplificado=True)
        assert open(out, 'rb').read(4) == b'%PDF'
    # todo tipo de carta desenha sem erro (Pokémon, Treinador, Energia, textos longos)
    from ptcg.carddb import db
    amostra = [c for c in db().cards][::7]
    assert IMP.gerar_pdf(amostra, simplificado=True, papel='A4')['paginas'] >= 1


def test_imagens_e_faltantes():
    from PIL import Image
    ids = ['TWM-130', 'TWM-130', 'MEG-114']
    original = IMP.arquivo_imagem
    with tempfile.TemporaryDirectory() as t:
        img = os.path.join(t, 'a.png')
        Image.new('RGB', (60, 84), (200, 30, 30)).save(img)
        from pathlib import Path
        try:
            IMP.arquivo_imagem = lambda cid: Path(img) if cid == 'TWM-130' else None
            r = IMP.gerar_pdf(ids, escala=0.9)
            assert len(r['faltando']) == 1 and 'Boss' in r['faltando'][0]                   # só a sem imagem cai no simplificado
            assert r['pdf'].count(b'/Subtype /Image') == 1                                  # imagem embutida uma vez, usada 2×
            assert not IMP.gerar_pdf(ids, simplificado=True)['faltando']
        finally:
            IMP.arquivo_imagem = original


def test_imagem_economica():
    """Fundo colorido vira papel branco; traços (texto) continuam escuros; o PDF sai em escala de cinza."""
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (300, 420), (230, 120, 30))                    # fundo laranja
    ImageDraw.Draw(im).rectangle((60, 200, 240, 212), fill=(255, 255, 255))   # "texto" claro sobre fundo
    e = IMP.imagem_economica(im)
    assert e.mode == 'L' and e.size == im.size
    assert e.getpixel((10, 10)) > 245                                     # fundo liso → branco
    assert min(e.crop((55, 195, 245, 217)).getdata()) < 150               # traço continua visível
    from pathlib import Path
    with tempfile.TemporaryDirectory() as t:
        img = os.path.join(t, 'a.png')
        im.save(img)
        original = IMP.arquivo_imagem
        try:
            IMP.arquivo_imagem = lambda cid: Path(img)
            r = IMP.gerar_pdf(['TWM-130'], economico=True)
            assert b'DeviceGray' in r['pdf'] and not r['faltando']
        finally:
            IMP.arquivo_imagem = original


if __name__ == '__main__':
    test_layout_e_papel()
    test_conjunto_e_ajuste()
    test_pdf_simplificado()
    test_imagens_e_faltantes()
    test_imagem_economica()
    print('ok')
