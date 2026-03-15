from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from .models import Season, SeasonPlayer
from playoffs.generator import bracket_size_for, generate_bracket
from playoffs.models import PlayoffBracket
from standings.calculator import calculate_standings


class SeasonPlayerInline(admin.TabularInline):
    model = SeasonPlayer
    extra = 1
    fields = ('player', 'tier', 'seed', 'is_active')
    autocomplete_fields = ('player',)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'status', 'num_tiers', 'sets_to_win', 'final_set_format', 'playoff_qualifiers_count')
    list_filter = ('status', 'year', 'final_set_format', 'walkover_rule')
    search_fields = ('name',)
    inlines = [SeasonPlayerInline]
    fieldsets = (
        (None, {'fields': ('name', 'year', 'status', 'num_tiers')}),
        ('Match Format', {'fields': ('sets_to_win', 'games_to_win_set', 'final_set_format')}),
        ('Playoffs', {'fields': ('playoff_qualifiers_count',)}),
        ('Points', {'fields': ('points_for_win', 'points_for_loss', 'points_for_walkover_loss')}),
        ('Rules', {'fields': ('walkover_rule', 'postponement_deadline', 'grace_period_days')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:season_id>/generate-playoffs/<int:tier>/',
                self.admin_site.admin_view(self.generate_playoffs_view),
                name='leagues_season_generate_playoffs',
            ),
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        season = get_object_or_404(Season, pk=object_id)
        generate_urls = []
        for tier in range(1, season.num_tiers + 1):
            generate_urls.append({
                'tier': tier,
                'url': reverse('admin:leagues_season_generate_playoffs', args=[object_id, tier]),
            })
        extra_context['generate_playoff_urls'] = generate_urls
        return super().change_view(request, object_id, form_url, extra_context)

    def generate_playoffs_view(self, request, season_id, tier):
        season = get_object_or_404(Season, pk=season_id)
        existing_bracket = PlayoffBracket.objects.filter(season=season, tier=tier).first()
        standings = calculate_standings(season, tier)
        max_q = min(season.playoff_qualifiers_count, len(standings))
        size = bracket_size_for(max_q)
        qualifiers = standings[:size]

        if request.method == 'POST' and not existing_bracket:
            try:
                generate_bracket(season, tier, request.user)
                messages.success(request, f'Tier {tier} playoff bracket generated successfully.')
                return HttpResponseRedirect(
                    reverse('leagues:playoffs_tier', kwargs={'pk': season_id, 'tier': tier})
                )
            except ValueError as e:
                messages.error(request, str(e))

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'tier': tier,
            'qualifiers': qualifiers,
            'bracket_size': size,
            'existing_bracket': existing_bracket,
            'title': f'Generate Tier {tier} Playoffs — {season.name}',
        }
        return render(request, 'playoffs/generate_playoffs.html', context)


@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(admin.ModelAdmin):
    list_display = ('player', 'season', 'tier', 'seed', 'is_active', 'joined_at')
    list_filter = ('season', 'tier', 'is_active')
    search_fields = ('player__username', 'player__first_name', 'player__last_name', 'season__name')
    autocomplete_fields = ('player', 'season')
