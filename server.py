"""Servidor local: interface (web/index.html) + API JSON do motor.

    python server.py            → abra http://localhost:8765
    python server.py --port 9000
"""
import argparse
import glob
import json
import os
import threading
import traceback
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ptcg.agents import make_agent
from ptcg import deckbuilder as DB
from ptcg import explorer as EX
from ptcg.carddb import db
from ptcg.decks import DECK_DIR, deck_to_text, list_decks, load_deck, parse_decklist, support_report, validate
from ptcg.engine import Game
from ptcg.logbook import registrar, registrar_problema, salvar_log_tcglive, salvar_partida_interface
from ptcg.view import card_info, game_cards, game_view

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, 'web')
LOCK = threading.Lock()
S = {'game': None, 'ctrl': ['human', 'heuristic'], 'agents': [None, None], 'decks': [None, None]}


def controllers():
    out = [{'id': 'human', 'label': 'Humano'}, {'id': 'heuristic', 'label': 'IA heurística'},
           {'id': 'random', 'label': 'Aleatório'}]
    for p in sorted(glob.glob(os.path.join(ROOT, 'checkpoints', '*.pt'))):
        rel = os.path.relpath(p, ROOT)
        out.append({'id': f'model:{rel}', 'label': f'Rede: {rel}'})
    return out


def deck_index():
    out = []
    for n in list_decks():
        try:
            d = load_deck(n, strict=False)
            rep = support_report(d.cards)
            out.append({'name': n, 'ok': not d.meta['errors'], 'errors': d.meta['errors'][:3],
                        'event': d.meta.get('event', ''), 'place': d.meta.get('place', ''),
                        'player': d.meta.get('player', ''), 'archetype': d.meta.get('archetype', ''),
                        'pending': [f'{x.name} ({s})' for x, _, s in rep]})
        except Exception as e:
            out.append({'name': n, 'ok': False, 'errors': [str(e)], 'pending': []})
    return out


def viewer():
    humans = [i for i in (0, 1) if S['ctrl'][i] == 'human']
    return humans[0] if len(humans) == 1 else 'all'


def state(reveal=False, with_cards=False):
    g = S['game']
    if g is None:
        return {'game': None}
    v = 'all' if reveal else viewer()
    ai_eval = None
    if not g.done:
        ag = S['agents'][g.prompt.player]
        if ag is not None and hasattr(ag, 'evaluate') and (v == 'all' or v == g.prompt.player):
            try:
                probs, value = ag.evaluate(g, g.prompt)
                ai_eval = {'probs': [round(float(x), 4) for x in probs], 'value': round(value, 3)}
            except Exception:
                traceback.print_exc()
    out = game_view(g, v, ai_eval)
    out.update(ctrl=S['ctrl'], viewer=v, decks=S['decks'])
    if with_cards:
        out['cards'] = game_cards(g)
    return out


def new_game(body):
    ctrl = [body.get('ctrl0', 'human'), body.get('ctrl1', 'heuristic')]
    seed = body.get('seed')
    seed = int(seed) if seed not in (None, '') else None
    decks = [load_deck(body['deck0']), load_deck(body['deck1'])]
    names = []
    for i in (0, 1):
        label = {'human': 'Você', 'heuristic': 'Heurística', 'random': 'Aleatório'}.get(ctrl[i], 'Rede')
        short = decks[i].meta.get('archetype') or decks[i].name
        names.append(f'{label} ({short})' if ctrl.count(ctrl[i]) == 1 else f'J{i + 1} ({short})')
    S['game'] = Game(decks[0].cards, decks[1].cards, seed=seed, names=names)
    S['ctrl'] = ctrl
    S['decks'] = [decks[0].name, decks[1].name]
    S['agents'] = [None if c == 'human' else make_agent(c, seed=(seed or 0) + i) for i, c in enumerate(ctrl)]
    S['logged'] = False
    S['comments'] = []


def log_if_done():
    g = S['game']
    if g is not None and g.done and not S.get('logged'):
        S['logged'] = True
        try:
            salvar_partida_interface(g, decks=S['decks'], controles=S['ctrl'],
                                     comentarios=[c['id'] for c in S.get('comments', [])])
        except Exception:
            traceback.print_exc()


def ai_step():
    g = S['game']
    if g is None or g.done:
        return False
    ag = S['agents'][g.prompt.player]
    if ag is None:
        return False
    g.step(ag.act(g, g.prompt))
    return True


def undo():
    g = S['game']
    if g is None or not g.history:
        return
    replay = Game(g.deck_lists[0], g.deck_lists[1], seed=g.seed, names=g.names)
    owners = []
    for i in g.history:
        owners.append(replay.prompt.player)
        replay.step(i)
    hist = list(g.history)
    while hist:
        who = owners[len(hist) - 1]
        hist.pop()
        if S['ctrl'][who] == 'human':
            break
    ng = Game(g.deck_lists[0], g.deck_lists[1], seed=g.seed, names=g.names)
    for i in hist:
        ng.step(i)
    S['game'] = ng


def run_replay(text):
    from ptcg.replay.replay import Replayer, replay_log
    from ptcg.replay.parse import parse_log
    best = replay_log(text)
    try:
        salvar_log_tcglive(text, best, origem='interface')
    except Exception:
        traceback.print_exc()
    rp = Replayer(parse_log(text))
    rp.forced = getattr(best, 'forced', {})
    rp.frames = []
    rep = rp.run()
    frames = rp.frames
    cards = game_cards(rep.game) if rep.game is not None else {}
    for f in frames:
        for p in f['state']['players']:
            for c in (p['hand'] or []) + p['discard']:
                if c['id'] not in cards and c['id'] in db().cards:
                    cards[c['id']] = card_info(db().get(c['id']))
    return {'summary': rep.summary(), 'frames': frames, 'cards': cards,
            'actions': [rep.actions_done, rep.actions_total], 'finished': rep.finished and not rep.divergence}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype='application/json', cache='no-store'):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if 'text' in ctype or 'json' in ctype else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', cache)
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        reveal = q.get('reveal', ['0'])[0] == '1'
        try:
            pages = {'/': 'welcome.html', '/welcome': 'welcome.html', '/jogar': 'index.html', '/index.html': 'index.html',
                     '/decks': 'decks.html', '/decks.html': 'decks.html', '/cartas': 'cartas.html', '/cartas.html': 'cartas.html'}
            if u.path in pages:
                with open(os.path.join(WEB, pages[u.path]), 'rb') as f:
                    return self._send(200, f.read(), 'text/html')
            if u.path.startswith('/img/'):
                partes = u.path.split('/')          # /img/<baixa|alta>/<ID>
                f = EX.arquivo_imagem(partes[2], partes[3]) if len(partes) == 4 else None
                if f is None:
                    return self._send(404, {'error': 'imagem não baixada (python baixar_imagens.py)'})
                return self._send(200, f.read_bytes(), 'image/webp' if f.suffix == '.webp' else 'image/png',
                                  cache='public, max-age=86400')
            if u.path == '/api/home':
                o = EX.opcoes()
                return self._send(200, {'cartas': o['total'], 'status': o['status'], 'com_imagem': o['com_imagem'],
                                        'decks': len(list_decks()), 'meus': len(list_decks('meus'))})
            if u.path == '/api/cards/options':
                return self._send(200, {**EX.opcoes(), 'categorias': DB.lista_categorias()})
            if u.path == '/api/cards/filter':
                g = lambda k: q.get(k, [''])[0]
                return self._send(200, EX.filtrar(g('q'), g('grupo'), g('sub'), g('status'), g('tipo'), g('estagio'),
                                                  g('colecao'), g('no_texto') == '1', int(g('offset') or 0)))
            if u.path == '/api/cards/detail':
                return self._send(200, EX.detalhe(q['id'][0]))
            if u.path == '/api/builder/init':
                return self._send(200, {'categorias': DB.lista_categorias(), 'decks': DB.decks_disponiveis(),
                                        'min_busca': DB.MIN_BUSCA})
            if u.path == '/api/builder/search':
                return self._send(200, DB.buscar(q.get('q', [''])[0], q.get('grupo', [''])[0], q.get('sub', [''])[0]))
            if u.path == '/api/builder/deck':
                return self._send(200, DB.ver_deck(q['name'][0]))
            if u.path == '/api/meta':
                D = db()
                cov = Counter(d.status for d in D.cards.values())
                return self._send(200, {'decks': deck_index(), 'controllers': controllers(),
                                        'coverage': dict(cov), 'total_cards': len(D.cards)})
            if u.path == '/api/deck':
                name = q['name'][0]
                d = load_deck(name, strict=False)
                return self._send(200, {'name': name, 'text': deck_to_text(d.cards, {k: v for k, v in d.meta.items()
                                                                                    if k not in ('errors', 'path')}),
                                        'errors': d.meta['errors'],
                                        'pending': [f'{x.name}: {s}' for x, _, s in support_report(d.cards)]})
            if u.path == '/api/state':
                with LOCK:
                    return self._send(200, state(reveal, with_cards=q.get('cards', ['0'])[0] == '1'))
            return self._send(404, {'error': 'não encontrado'})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            body = self._body()
            reveal = bool(body.get('reveal'))
            if u.path == '/api/replay':
                return self._send(200, run_replay(body['log']))
            if u.path.startswith('/api/builder/'):
                try:
                    if u.path == '/api/builder/eval':
                        return self._send(200, DB.avaliar(body['cards']))
                    if u.path == '/api/builder/save':
                        return self._send(200, DB.salvar(body['name'], body['cards'], bool(body.get('overwrite')),
                                                         body.get('meta')))
                    if u.path == '/api/builder/duplicate':
                        return self._send(200, DB.duplicar(body['origem'], body.get('destino') or None))
                except (ValueError, FileExistsError, KeyError) as e:
                    return self._send(400, {'error': str(e).strip("'\"")})
                return self._send(404, {'error': 'não encontrado'})
            with LOCK:
                with_cards = False
                if u.path == '/api/new':
                    new_game(body)
                    with_cards = True
                elif u.path == '/api/act':
                    g = S['game']
                    if g is None or g.done:
                        return self._send(400, {'error': 'sem partida em andamento'})
                    if S['ctrl'][g.prompt.player] != 'human':
                        return self._send(400, {'error': 'não é a vez de um humano'})
                    g.step(int(body['index']))
                elif u.path == '/api/step':
                    for _ in range(int(body.get('n', 1))):
                        if not ai_step():
                            break
                elif u.path == '/api/comment':
                    g = S['game']
                    texto = (body.get('text') or '').strip()
                    if g is None or not texto:
                        return self._send(400, {'error': 'sem partida ou comentário vazio'})
                    rec = registrar_problema(g, texto, decks=S['decks'], controles=S['ctrl'])
                    S.setdefault('comments', []).append({'id': rec['id']})
                    return self._send(200, {'ok': True, 'id': rec['id']})
                elif u.path == '/api/undo':
                    undo()
                elif u.path == '/api/deck':
                    name = ''.join(ch for ch in body['name'] if ch.isalnum() or ch in '_-') or 'meu_deck'
                    deck, errs = parse_decklist(body['text'], name)
                    errs += validate(deck.cards)
                    if errs:
                        return self._send(400, {'error': '\n'.join(errs)})
                    (DECK_DIR / 'meus').mkdir(parents=True, exist_ok=True)
                    (DECK_DIR / 'meus' / f'{name}.txt').write_text(deck_to_text(deck.cards), encoding='utf-8')
                    registrar('decks', f'salvou meus/{name}.txt pela interface')
                    return self._send(200, {'ok': True, 'name': f'meus/{name}',
                                            'pending': [f'{x.name}: {s}' for x, _, s in support_report(deck.cards)]})
                else:
                    return self._send(404, {'error': 'não encontrado'})
                log_if_done()
                return self._send(200, state(reveal, with_cards))
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    db()   # carrega a base antes do primeiro acesso
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    url = f'http://localhost:{a.port}'
    print(f'Servidor em {url}  (Ctrl+C para sair)')
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
