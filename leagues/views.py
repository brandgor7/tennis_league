from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, View

from .models import Season, SeasonPlayer

User = get_user_model()
from matches.models import Match
from standings.calculator import calculate_standings


def home(request):
    last_slug = request.COOKIES.get('last_season')
    if last_slug:
        season = Season.objects.filter(slug=last_slug).first()
        if season:
            return redirect('leagues:standings', slug=season.slug)
    return render(request, 'home.html')


class SeasonListView(ListView):
    model = Season
    template_name = 'leagues/season_list.html'
    context_object_name = 'seasons'
    ordering = ['-year', 'name']


class SeasonDetailView(DetailView):
    model = Season
    template_name = 'leagues/season_detail.html'
    context_object_name = 'season'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'



class SeasonPlayerDetailView(View):
    def get(self, request, slug, username):
        season = get_object_or_404(Season, slug=slug)
        player = get_object_or_404(User, username=username)
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
            'tier_name': season.tier_name(tier),
            'standing': standing,
            'rank': rank,
            'upcoming': upcoming,
            'results': results,
        })
