from django.db.models import F
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, DetailView

from leagues.models import Season
from .models import Match


class MatchupsView(TemplateView):
    template_name = 'matches/matchups.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, pk=self.kwargs['pk'])
        qs = (
            Match.objects
            .filter(season=season, status__in=[Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED])
            .select_related('player1', 'player2', 'winner')
            .order_by(F('scheduled_date').asc(nulls_last=True), 'created_at')
        )
        multi_tier = season.num_tiers > 1
        tiers = [
            (tier_num, qs.filter(tier=tier_num))
            for tier_num in range(1, season.num_tiers + 1)
        ] if multi_tier else [(1, qs)]
        ctx['season'] = season
        ctx['tiers'] = tiers
        ctx['multi_tier'] = multi_tier
        return ctx


class ResultsView(TemplateView):
    template_name = 'matches/results.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, pk=self.kwargs['pk'])
        qs = (
            Match.objects
            .filter(season=season, status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER])
            .select_related('player1', 'player2', 'winner')
            .order_by(F('played_date').desc(nulls_last=True), '-created_at')
        )
        multi_tier = season.num_tiers > 1
        tiers = [
            (tier_num, qs.filter(tier=tier_num))
            for tier_num in range(1, season.num_tiers + 1)
        ] if multi_tier else [(1, qs)]
        ctx['season'] = season
        ctx['tiers'] = tiers
        ctx['multi_tier'] = multi_tier
        return ctx


class MatchDetailView(DetailView):
    model = Match
    template_name = 'matches/match_detail.html'
    context_object_name = 'match'

    def get_queryset(self):
        return Match.objects.select_related('player1', 'player2', 'winner', 'season')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['season'] = self.object.season
        ctx['multi_tier'] = self.object.season.num_tiers > 1
        ctx['sets'] = self.object.sets.all()
        return ctx
