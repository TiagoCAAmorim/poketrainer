"""Leitor do log exportado pelo Pokémon TCG Live (botão "Copy Log").

Os modelos de frase (templates/*.json) vêm do projeto ptcgl-battle-log-parser (licença MIT).
Suporta inglês e português (o cliente em PT-BR escreve os nomes das cartas em português;
eles são convertidos para o nome em inglês usado pela base de cartas).

    log = parse_log(open('partida.log').read())
    for turn in log.turns: ...
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / 'templates'
LOCALES = {'en': 'blog-templates.en.json', 'pt': 'blog-templates.ptbr.json'}


@dataclass
class Event:
    key: str                     # ex.: 'blog_loc_played_to_bench'
    f: dict                      # campos do template (playerName, cardName, ...)
    line: str
    depth: int = 0               # 0 = ação principal, 1 = sub-evento ("- ...")
    cards: list = field(default_factory=list)   # lista "• A, B, C" logo abaixo
    subs: list = field(default_factory=list)     # sub-eventos de uma ação principal
    breakdown: list = field(default_factory=list)

    def __repr__(self):
        return f'<{self.key} {self.f}{" " + str(self.cards) if self.cards else ""}>'


@dataclass
class Phase:
    kind: str                    # setup | turn | checkup
    player: str | None
    events: list = field(default_factory=list)


@dataclass
class BattleLog:
    locale: str
    players: list
    phases: list
    winner: str | None = None
    end_reason: str = ''
    unmatched: list = field(default_factory=list)

    @property
    def turns(self):
        return [p for p in self.phases if p.kind == 'turn']


class _Templates:
    def __init__(self, locale):
        data = json.load(open(TEMPLATE_DIR / LOCALES[locale], encoding='utf-8'))
        self.raw = {k: v['template'] for k, v in data.items()}
        self.rx = []
        for key, tpl in data.items():
            t = tpl['template'].strip()
            if '[' not in t and len(t) < 25:
                continue
            pat = ''
            last = 0
            names = []
            for m in re.finditer(r'\[(\w+)\]', t):
                pat += re.escape(t[last:m.start()])
                nm = m.group(1)
                if nm in names:
                    pat += f'(?P={nm})'
                else:
                    pat += f'(?P<{nm}>.+?)'
                    names.append(nm)
                last = m.end()
            pat += re.escape(t[last:])
            pat = re.sub("['’]", "\x00", pat).replace('\x00', "['’]").replace('\\ ', r'\s+')
            literal = len(re.sub(r'\[\w+\]', '', t))
            self.rx.append((literal, key, re.compile('^' + pat + r'\.?$')))
        self.rx.sort(key=lambda x: -x[0])

    def match(self, line):
        for _, key, rx in self.rx:
            m = rx.match(line)
            if m:
                return key, {k: v.strip() for k, v in m.groupdict().items()}
        return None, None


_CACHE = {}


def templates(locale):
    if locale not in _CACHE:
        _CACHE[locale] = _Templates(locale)
    return _CACHE[locale]


def detect_locale(text):
    if re.search(r'^Preparação\s*$', text, re.M) or re.search(r'^Turno de ', text, re.M):
        return 'pt'
    return 'en'


def _name_map_pt():
    from ..carddb import db, norm
    m = {}
    for d in db().cards.values():
        if d.name_pt:
            m[norm(d.name_pt)] = d.name
    return m


def parse_log(text: str) -> BattleLog:
    loc = detect_locale(text)
    T = templates(loc)
    ptmap = _name_map_pt() if loc == 'pt' else None
    phases: list[Phase] = []
    cur = Phase('setup', None)
    players: list[str] = []
    last_main = None
    last_ev = None
    unmatched = []
    winner = None
    end_reason = ''
    in_breakdown = False
    turn_rx = re.compile('^' + re.sub("['’]", "['’]", re.escape(T.raw['blog_loc_phase_turn'])
                                      .replace(r'\[playerName\]', '(.+?)')) + '$')
    setup_word = T.raw['blog_loc_phase_setup'].strip()
    checkup_word = T.raw['blog_loc_phase_checkup'].strip()
    breakdown_label = T.raw['blog_loc_export_damage_breakdown_label'].strip().rstrip(':')

    def fix_names(f):
        if ptmap is None:
            return f
        from ..carddb import norm
        out = {}
        for k, v in f.items():
            out[k] = ptmap.get(norm(v), v) if 'Name' in k and 'player' not in k.lower() else v
        return out

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            in_breakdown = False
            continue
        s = line.strip()
        if s == setup_word:
            cur = Phase('setup', None)
            phases.append(cur)
            continue
        if s == checkup_word:
            cur = Phase('checkup', None)
            phases.append(cur)
            continue
        m = turn_rx.match(s)
        if m:
            cur = Phase('turn', m.group(1))
            phases.append(cur)
            if m.group(1) not in players:
                players.append(m.group(1))
            continue
        if s.startswith('•'):
            items = [x.strip() for x in s.lstrip('•').split(',') if x.strip()]
            if ptmap is not None:
                from ..carddb import norm
                items = [ptmap.get(norm(x), x) for x in items]
            if in_breakdown and last_ev is not None:
                last_ev.breakdown += items
            elif last_ev is not None:
                last_ev.cards += items
            continue
        depth = 0
        if s.startswith('- '):
            depth, s = 1, s[2:].strip()
        if s.rstrip(':') == breakdown_label:
            in_breakdown = True
            continue
        in_breakdown = False
        if not phases:
            phases.append(cur)
        mend = re.match(r'^(.*?)\.\s*(\S.*?) wins\.?$', s) if loc == 'en' else \
            re.match(r'^(.*?)\.\s*(\S.*?) (?:venceu|vence)\.?$', s)
        if mend:
            end_reason, winner = mend.group(1), mend.group(2)
            continue
        key, f = T.match(s)
        if key is None:
            unmatched.append(s)
            continue
        f = fix_names(f)
        ev = Event(key, f, s, depth)
        if key == 'blog_loc_draw_opening_hand' and f.get('playerName') not in players:
            players.append(f['playerName'])
        if depth == 1 and last_main is not None:
            last_main.subs.append(ev)
        else:
            cur.events.append(ev)
            last_main = ev
        last_ev = ev
    return BattleLog(loc, players, phases, winner, end_reason, unmatched)
