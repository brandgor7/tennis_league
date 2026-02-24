from django.contrib import admin
from .models import Season, SeasonPlayer


class SeasonPlayerInline(admin.TabularInline):
    model = SeasonPlayer
    extra = 1
    fields = ('player', 'seed', 'is_active')
    autocomplete_fields = ('player',)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'status', 'sets_to_win', 'final_set_format', 'playoff_qualifiers_count')
    list_filter = ('status', 'year', 'final_set_format', 'walkover_rule')
    search_fields = ('name',)
    inlines = [SeasonPlayerInline]
    fieldsets = (
        (None, {'fields': ('name', 'year', 'status')}),
        ('Match Format', {'fields': ('sets_to_win', 'final_set_format')}),
        ('Playoffs', {'fields': ('playoff_qualifiers_count',)}),
        ('Points', {'fields': ('points_for_win', 'points_for_loss', 'points_for_walkover_loss')}),
        ('Rules', {'fields': ('walkover_rule', 'postponement_deadline')}),
    )


@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(admin.ModelAdmin):
    list_display = ('player', 'season', 'seed', 'is_active', 'joined_at')
    list_filter = ('season', 'is_active')
    search_fields = ('player__username', 'player__first_name', 'player__last_name', 'season__name')
    autocomplete_fields = ('player', 'season')
