from django import forms
from django.contrib import admin
from .models import Match, MatchSet


class MatchSetInline(admin.TabularInline):
    model = MatchSet
    extra = 0
    fields = ('set_number', 'player1_games', 'player2_games', 'tiebreak_player1_points', 'tiebreak_player2_points')


class MatchAdminForm(forms.ModelForm):
    player1_is_external = forms.BooleanField(
        required=False,
        label='Player 1 is an external player (not in the system)',
    )
    player2_is_external = forms.BooleanField(
        required=False,
        label='Player 2 is an external player (not in the system)',
    )

    class Meta:
        model = Match
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['player1'].required = False
        self.fields['player2'].required = False
        if self.instance and self.instance.pk:
            self.fields['player1_is_external'].initial = bool(self.instance.external_player1_name)
            self.fields['player2_is_external'].initial = bool(self.instance.external_player2_name)

    def clean(self):
        cleaned = super().clean()
        for side in ('1', '2'):
            is_external = cleaned.get(f'player{side}_is_external')
            player = cleaned.get(f'player{side}')
            name = (cleaned.get(f'external_player{side}_name') or '').strip()
            if is_external:
                if not name:
                    self.add_error(f'external_player{side}_name', 'Enter a name for the external player.')
                if player:
                    self.add_error(f'player{side}', 'Cannot select a roster player and mark this side external — choose one.')
            else:
                cleaned[f'external_player{side}_name'] = ''
        return cleaned


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/admin_match_form.js',)

    form = MatchAdminForm
    list_display = ('match_players', 'season', 'tier', 'round', 'status', 'scheduled_date', 'played_date', 'winner_name')
    list_filter = ('season', 'tier', 'status', 'round')
    search_fields = (
        'player1__username', 'player1__first_name', 'player1__last_name',
        'player2__username', 'player2__first_name', 'player2__last_name',
        'external_player1_name', 'external_player2_name',
    )
    autocomplete_fields = ('season', 'player1', 'player2', 'winner', 'entered_by', 'confirmed_by')
    inlines = [MatchSetInline]
    fieldsets = (
        (None, {'fields': (
            'season', 'tier', 'round',
            'player1', 'player1_is_external', 'external_player1_name',
            'player2', 'player2_is_external', 'external_player2_name',
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
