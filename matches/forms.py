from django import forms
from django.contrib.auth import get_user_model

from leagues.models import SeasonPlayer
from .models import Match

User = get_user_model()


class MatchScheduleForm(forms.ModelForm):
    """
    Form for scheduling a match within a season.

    Player dropdowns are filtered to the requested tier at the view level
    (pass `tier` and `season` to __init__); cross-tier pairings are also
    blocked at validation time.
    """

    class Meta:
        model = Match
        fields = ['player1', 'player2', 'tier', 'scheduled_date']
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, season=None, tier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.season = season
        self.requested_tier = tier

        if season is not None:
            if tier is not None:
                # Filter dropdowns to the requested tier
                players_qs = User.objects.filter(
                    season_players__season=season,
                    season_players__tier=tier,
                    season_players__is_active=True,
                ).order_by('last_name', 'first_name')
                self.fields['tier'].initial = tier
                self.fields['tier'].widget = forms.HiddenInput()
            else:
                # No tier filter — show all active players in the season
                players_qs = User.objects.filter(
                    season_players__season=season,
                    season_players__is_active=True,
                ).order_by('last_name', 'first_name')
            self.fields['player1'].queryset = players_qs
            self.fields['player2'].queryset = players_qs

    def clean(self):
        cleaned = super().clean()
        player1 = cleaned.get('player1')
        player2 = cleaned.get('player2')
        tier = cleaned.get('tier')

        if player1 and player2 and self.season and tier is not None:
            p1_tier = (
                SeasonPlayer.objects.filter(
                    season=self.season, player=player1, is_active=True
                )
                .values_list('tier', flat=True)
                .first()
            )
            p2_tier = (
                SeasonPlayer.objects.filter(
                    season=self.season, player=player2, is_active=True
                )
                .values_list('tier', flat=True)
                .first()
            )
            if p1_tier is not None and p2_tier is not None and p1_tier != p2_tier:
                raise forms.ValidationError(
                    'Both players must be in the same tier to schedule a match.'
                )

        return cleaned
