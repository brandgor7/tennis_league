from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from leagues.models import Season
from .generator import _ROUND_SEQUENCE
from .models import PlayoffBracket
from matches.models import Match


_ROUND_LABELS = {
    Match.ROUND_R32: 'Round of 32',
    Match.ROUND_R16: 'Round of 16',
    Match.ROUND_QF: 'Quarterfinal',
    Match.ROUND_SF: 'Semifinal',
    Match.ROUND_FINAL: 'Final',
}


def _bracket_context(bracket):
    """
    Build the rounds_data and bracket_size needed to render a bracket template.

    Returns (rounds_data, bracket_size) where rounds_data is a list of dicts:
      {code, label, slots, col_index}
    and each slot has .grid_row_start / .grid_row_end set.
    """
    slots_qs = (
        bracket.slots
        .select_related('match', 'match__player1', 'match__player2', 'match__winner')
        .prefetch_related('match__sets')
        .order_by('bracket_position')
    )

    # Group by round, preserving _ROUND_SEQUENCE order
    by_round = {}
    for slot in slots_qs:
        by_round.setdefault(slot.round, []).append(slot)

    ordered_rounds = [(r, by_round[r]) for r in _ROUND_SEQUENCE if r in by_round]

    if not ordered_rounds:
        return [], 0

    first_round_count = len(ordered_rounds[0][1])
    bracket_size = first_round_count * 2

    rounds_data = []
    for col_idx, (round_code, slots) in enumerate(ordered_rounds):
        n_matches = len(slots)
        span = bracket_size // n_matches
        for i, slot in enumerate(slots):
            slot.grid_row_start = i * span + 1
            slot.grid_row_end = (i + 1) * span + 1
        rounds_data.append({
            'code': round_code,
            'label': _ROUND_LABELS[round_code],
            'col_index': col_idx + 1,
            'slots': slots,
        })

    return rounds_data, bracket_size


class PlayoffListView(TemplateView):
    template_name = 'playoffs/bracket_list.html'

    def get(self, request, slug):
        season = get_object_or_404(Season, slug=slug)
        if season.num_tiers == 1:
            return redirect('leagues:playoffs_tier', slug=slug, tier=1)
        brackets_by_tier = {
            b.tier: b
            for b in PlayoffBracket.objects.filter(season=season)
        }
        tier_brackets = [
            (t, brackets_by_tier.get(t))
            for t in range(1, season.num_tiers + 1)
        ]
        return self.render_to_response({
            'season': season,
            'tier_brackets': tier_brackets,
        })


class PlayoffBracketView(TemplateView):
    template_name = 'playoffs/bracket.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, slug=self.kwargs['slug'])
        tier = self.kwargs['tier']
        bracket = get_object_or_404(PlayoffBracket, season=season, tier=tier)
        rounds_data, bracket_size = _bracket_context(bracket)
        ctx.update({
            'season': season,
            'bracket': bracket,
            'tier': tier,
            'multi_tier': season.num_tiers > 1,
            'tier_range': range(1, season.num_tiers + 1),
            'rounds_data': rounds_data,
            'bracket_size': bracket_size,
            'num_rounds': len(rounds_data),
        })
        return ctx
