from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, View

from .models import Season, SeasonPlayer

User = get_user_model()
from matches.models import Match
from standings.calculator import calculate_standings


def home(request):
    active_season = Season.objects.filter(status=Season.STATUS_ACTIVE).first()
    if active_season:
        return redirect('leagues:standings', pk=active_season.pk)
    return redirect('leagues:season_list')


class SeasonListView(ListView):
    model = Season
    template_name = 'leagues/season_list.html'
    context_object_name = 'seasons'
    ordering = ['-year', 'name']


class SeasonDetailView(DetailView):
    model = Season
    template_name = 'leagues/season_detail.html'
    context_object_name = 'season'


class SeasonPlayerListView(View):
    def get(self, request, pk):
        season = get_object_or_404(Season, pk=pk)
        season_players = (
            SeasonPlayer.objects
            .filter(season=season, is_active=True)
            .select_related('player')
            .order_by('tier', 'player__last_name', 'player__first_name')
        )

        tiers = []
        for tier_num in range(1, season.num_tiers + 1):
            players = [sp for sp in season_players if sp.tier == tier_num]
            tiers.append((tier_num, players))

        return render(request, 'leagues/player_list.html', {
            'season': season,
            'tiers': tiers,
            'multi_tier': season.num_tiers > 1,
        })


class SeasonPlayerDetailView(View):
    def get(self, request, pk, player_pk):
        season = get_object_or_404(Season, pk=pk)
        player = get_object_or_404(User, pk=player_pk)
        season_player = get_object_or_404(SeasonPlayer, season=season, player=player, is_active=True)

        tier = season_player.tier
        standings_rows = calculate_standings(season, tier)
        standing = None
        rank = None
        for i, row in enumerate(standings_rows, start=1):
            if row['player'].pk == player.pk:
                standing = row
                rank = i
                break

        upcoming = (
            Match.objects
            .filter(
                Q(player1=player) | Q(player2=player),
                season=season,
                status__in=[Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED, Match.STATUS_PENDING],
            )
            .select_related('player1', 'player2', 'winner', 'season')
            .order_by('scheduled_date')
        )

        results = (
            Match.objects
            .filter(
                Q(player1=player) | Q(player2=player),
                season=season,
                status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER],
            )
            .select_related('player1', 'player2', 'winner', 'season')
            .prefetch_related('sets')
            .order_by('-played_date', '-created_at')
        )

        return render(request, 'leagues/player_detail.html', {
            'season': season,
            'player': player,
            'season_player': season_player,
            'standing': standing,
            'rank': rank,
            'upcoming': upcoming,
            'results': results,
        })
