from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from leagues.models import Season
from .generator import _ROUND_SEQUENCE, generate_bracket
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
    Build the rounds_data and bracket_size needed to render a bracket.

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


class PlayoffView(TemplateView):
    template_name = 'playoffs/bracket.html'

    def get(self, request, *args, **kwargs):
        season = get_object_or_404(Season, slug=kwargs['slug'])
        if not season.playoffs_public and not request.user.is_staff:
            raise PermissionDenied
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season.objects.prefetch_related('tiers'), slug=self.kwargs['slug'])

        brackets_by_tier = {
            b.tier: b for b in PlayoffBracket.objects.filter(season=season)
        }

        tiers_data = []
        for t in range(1, season.num_tiers + 1):
            bracket = brackets_by_tier.get(t)
            if bracket:
                rounds_data, bracket_size = _bracket_context(bracket)
            else:
                rounds_data, bracket_size = [], 0
            tiers_data.append({
                'tier_num': t,
                'tier_name': season.tier_name(t),
                'bracket': bracket,
                'rounds_data': rounds_data,
                'bracket_size': bracket_size,
                'num_rounds': len(rounds_data),
            })

        ctx.update({
            'season': season,
            'tiers_data': tiers_data,
            'multi_tier': season.num_tiers > 1,
        })
        return ctx


@method_decorator(login_required, name='dispatch')
class PlayoffBracketRefreshView(View):
    def post(self, request, slug, tier):
        if not request.user.is_staff:
            raise PermissionDenied
        season = get_object_or_404(Season.objects.prefetch_related('tiers'), slug=slug)
        bracket = get_object_or_404(PlayoffBracket, season=season, tier=tier)

        first_slot = bracket.slots.select_related('match').order_by('bracket_position').first()
        start_date = first_slot.match.scheduled_date if first_slot else None

        bracket.delete()

        try:
            generate_bracket(season, tier, request.user, start_date=start_date)
            messages.success(request, f'{season.tier_name(tier)} bracket refreshed from current standings.')
        except ValueError as e:
            messages.error(request, str(e))

        return redirect('leagues:playoffs', slug=slug)
