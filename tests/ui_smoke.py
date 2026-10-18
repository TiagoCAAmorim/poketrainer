"""Teste de fumaça das páginas web (precisa do servidor no ar e de playwright: pip install -r requirements-dev.txt).

    python server.py --no-browser &      python tests/ui_smoke.py [http://localhost:8765] [pasta_para_capturas]
"""
import sys
from playwright.sync_api import sync_playwright
B=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8765'; S=sys.argv[2] if len(sys.argv)>2 else '.'
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1400,'height':850})
    errs=[]; pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None); pg.on('pageerror',lambda e: errs.append('PAGEERR '+str(e)))
    pg.goto(B+'/'); pg.wait_for_timeout(800); pg.screenshot(path=f'{S}/welcome.png')
    print('stats:',pg.inner_text('#stats'))
    pg.goto(B+'/cartas'); pg.wait_for_timeout(1500)
    print('count:',pg.inner_text('#count'), 'tiles',pg.locator('.tile').count())
    pg.click('#segStatus button[data-v="problema"]'); pg.wait_for_timeout(800)
    print('problema:',pg.inner_text('#count'))
    pg.click('.tile >> nth=0'); pg.wait_for_timeout(800); pg.screenshot(path=f'{S}/cartas.png')
    print('detail:',pg.inner_text('#dbody')[:200].replace('\n',' | '))
    pg.keyboard.press('Escape'); pg.fill('#q','dragap'); pg.click('#limpar') if False else None
    pg.goto(B+'/decks'); pg.wait_for_timeout(1500)
    print('src rows',pg.locator('#srcList .row').count())
    pg.locator('#srcList [data-act=add]').first.click(); pg.locator('#srcList [data-act=add]').nth(1).click(modifiers=['Shift'])
    print('total',pg.inner_text('#total'))
    pg.click('[data-tab=busca]'); pg.fill('#fNome','ultra'); pg.wait_for_timeout(700)
    print('busca rows',pg.locator('#srcList .row').count()); pg.screenshot(path=f'{S}/decks.png')
    pg.goto(B+'/jogar'); pg.wait_for_timeout(1500); print('decks no jogo',pg.locator('#deck0 option').count())
    print('ERROS JS:',errs)
    assert not errs
    b.close()
