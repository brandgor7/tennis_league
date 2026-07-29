from django.contrib import admin
from .models import Match, MatchSet


class MatchSetInline(admin.TabularInline):
    model = MatchSet
    extra = 0
    fields = ('set_number', 'player1_games', 'player2_games', 'tiebreak_player1_points', 'tiebreak_player2_points')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/admin_match_form.js',)

    list_display = ('match_players', 'season', 'tier', 'round', 'status', 'scheduled_date', 'played_date', 'winner_name')
    list_filter = ('season', 'tier', 'status', 'round')
    search_fields = (
        'player1__username', 'player1__first_name', 'player1__last_name',
        'player2__username', 'player2__first_name', 'player2__last_name',
    )
    autocomplete_fields = ('season', 'player1', 'player2', 'winner', 'entered_by', 'confirmed_by')
    inlines = [MatchSetInline]
    fieldsets = (
        (None, {'fields': (
            'season', 'tier', 'round',
            'player1', 'player1_is_external',
            'player2', 'player2_is_external',
        )}),
        ('Schedule', {'fields': ('scheduled_date', 'played_date', 'status')}),
        ('Result', {'fields': ('winner', 'winner_is_external', 'entered_by', 'confirmed_by')}),
        ('Notes', {'fields': ('walkover_reason', 'notes')}),
    )

    @admin.display(description='Match')
    def match_players(self, obj):
        return f'{obj.player1_display_name} vs {obj.player2_display_name}'

    @admin.display(description='Winner')
    def winner_name(self, obj):
        return obj.winner_display_name


@admin.register(MatchSet)
class MatchSetAdmin(admin.ModelAdmin):
    list_display = ('match', 'set_number', 'player1_games', 'player2_games', 'tiebreak_player1_points', 'tiebreak_player2_points')
    list_filter = ('match__season',)
    search_fields = ('match__player1__username', 'match__player2__username')
