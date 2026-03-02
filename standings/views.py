from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from leagues.models import Season
from .calculator import calculate_standings


class StandingsView(TemplateView):
    template_name = 'standings/standings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, pk=self.kwargs['pk'])
        tiers = [
            (tier_num, calculate_standings(season, tier_num))
            for tier_num in range(1, season.num_tiers + 1)
        ]
        ctx['season'] = season
        ctx['tiers'] = tiers          # list of (tier_number, standings_rows)
        ctx['multi_tier'] = season.num_tiers > 1
        return ctx
