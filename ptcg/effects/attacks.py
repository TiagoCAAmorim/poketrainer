"""Efeitos escritos à mão: attacks."""
from __future__ import annotations

from ..core import AttackImpl
from . import attack


@attack('Slowking', 'Seek Inspiration')
def _(d, atk):
    """Descarta o topo; se for Pokémon sem Regra, usa um dos ataques dele como este ataque."""
    def run_(g, ctx):
        pl = g.players[ctx.player]
        if not pl.deck:
            return
        c = pl.deck.pop(0)
        pl.discard.append(c)
        g.say(f'Seek Inspiration descartou {c.name}')
        if c.d.kind != 'pokemon' or c.d.rule_box or not c.d.attacks:
            return
        opts = c.d.attacks
        from ..core import Option
        o = yield from g.ask(ctx.player, 'copy_attack', f'Usar qual ataque de {c.name}?',
                             [Option(a.name, a, 'text') for a in opts], c)
        a = o.value
        ctx.attack = a
        ctx.damage = a.damage
        im = a.impl
        if im is not None and im.run is not None:
            yield from g.run_attack_impl(ctx, im) if hasattr(g, 'run_attack_impl') else im.run(g, ctx)
            return
        if im is not None and im.pre is not None:
            from ..engine import run
            yield from run(im.pre(g, ctx))
        if not ctx.no_damage:
            yield from g.main_damage(ctx)
        if im is not None and im.post is not None and not ctx.no_damage:
            from ..engine import run
            yield from run(im.post(g, ctx))
    return AttackImpl(run=run_)
