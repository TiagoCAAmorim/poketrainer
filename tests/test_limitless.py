"""Testes do leitor de HTML da Limitless com marcações de exemplo (sem rede)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.limitless import classify, parse_decklist_page, parse_standings, parse_tournament_list  # noqa: E402

LIST = '''<table><tr><th>Date</th></tr>
<tr><td>10 Oct 26</td><td><img src="/flags/US.png"></td><td><a href="/tournaments/581">Regional Louisville, KY</a></td>
<td><img alt="Standard"></td><td>2927</td><td><a href="/players/1">Riley McKay</a></td></tr>
<tr><td>20 Sep 26</td><td></td><td><a href="/tournaments/569">Champions League Yokohama</a></td>
<td><img alt="Standard (JP)" class="format-jp"></td><td>5000</td><td></td></tr>
<tr><td>28 Aug 26</td><td></td><td><a href="https://limitlesstcg.com/tournaments/515">World Championships 2026</a></td>
<td></td><td>797</td><td></td></tr></table>'''

STANDINGS = '''<table class="data-table"><tr><th>#</th></tr>
<tr data-placing="2"><td>2</td><td><a href="/players/77">Austin Charles</a></td><td></td>
<td><a href="/decks/1?variant=2"><img src="https://r2.limitlesstcg.net/pokemon/gen9/dragapult.png"><img src="https://r2.limitlesstcg.net/pokemon/gen9/blaziken.png"></a></td>
<td><a href="/decks/list/30160">List</a></td></tr>
<tr><td>1</td><td><a href="/players/5">Riley McKay</a></td><td></td>
<td><img src="https://r2.limitlesstcg.net/pokemon/gen9/dragapult.png"></td><td><a href="/decks/list/29678">List</a></td></tr>
<tr><td>9</td><td><a href="/players/9">Someone</a></td><td></td><td></td><td><a href="/decks/list/1">List</a></td></tr></table>'''

DECK_A = '''<div class="decklist-column"><div class="decklist-card" data-set="TWM" data-number="128" data-lang="en">
<span class="card-count">4</span> <span class="card-name">Dreepy</span></div>
<div class="decklist-card" data-set="MEE" data-number="10"><span class="card-count">3</span><span class="card-name">Fire Energy</span></div></div>'''

DECK_B = '''<a href="https://limitlesstcg.com/cards/TWM/130"><span>3</span> Dragapult ex <img alt="TWM"></a>
<a href="https://www.tcgplayer.com/x">$1.00</a>
<a href="/cards/MEG/119">4 Lillie&#39;s Determination</a>'''


def test_tournament_list():
    ts = parse_tournament_list(LIST)
    assert [t['id'] for t in ts] == [581, 569, 515]
    assert ts[0]['players'] == 2927 and ts[0]['date'] == '10 Oct 26'
    assert ts[1]['format'] == 'standard_jp'
    assert [classify(t['name']) for t in ts] == ['regional', 'champions_league', 'world']


def test_standings():
    st = parse_standings(STANDINGS, 8)
    assert [(r['place'], r['player'], r['list_id']) for r in st] == [(1, 'Riley McKay', 29678), (2, 'Austin Charles', 30160)]
    assert st[1]['archetype'] == 'Dragapult / Blaziken'


def test_decklist_formats():
    assert parse_decklist_page(DECK_A) == [(4, 'Dreepy', 'TWM', '128'), (3, 'Fire Energy', 'MEE', '10')]
    assert parse_decklist_page(DECK_B) == [(3, 'Dragapult ex', 'TWM', '130'), (4, "Lillie's Determination", 'MEG', '119')]


if __name__ == '__main__':
    test_tournament_list()
    test_standings()
    test_decklist_formats()
    print('ok')
