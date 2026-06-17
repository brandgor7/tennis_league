import datetime

from django.contrib.auth import get_user_model
from django.db.models import Q, F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, TemplateView, View

from .models import Season, SeasonPlayer, Team

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
        team = Team.objects.filter(season=season, tier=tier, members=player).first()
        standings_rows = calculate_standings(season, tier)
        standing = None
        rank = None
        if team:
            for i, row in enumerate(standings_rows, start=1):
                if row['participant'].pk == team.pk:
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
            .order_by(F('scheduled_date').desc(nulls_last=True), '-created_at')
        )

        today = datetime.date.today()
        mode = season.schedule_display_mode
        if mode == Season.DISPLAY_CURRENT_DAY:
            upcoming = upcoming.filter(
                Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=today)
            )
        elif mode == Season.DISPLAY_CURRENT_WEEK:
            week_end = today + datetime.timedelta(days=6 - today.weekday())
            upcoming = upcoming.filter(
                Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=week_end)
            )
        elif mode == Season.DISPLAY_NEXT_X_DAYS:
            cutoff = today + datetime.timedelta(days=season.schedule_display_days)
            upcoming = upcoming.filter(
                Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=cutoff)
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


class RulesView(TemplateView):
    template_name = 'leagues/rules.html'

    def dispatch(self, request, *args, **kwargs):
        season = get_object_or_404(Season, slug=kwargs['slug'])
        if not season.show_rules:
            raise Http404
        self.season = season
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['rules_content'] = self.season.rules_content
        return ctx
