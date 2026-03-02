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
            tier_map = dict(
                SeasonPlayer.objects.filter(
                    season=self.season,
                    player__in=[player1, player2],
                    is_active=True,
                ).values_list('player_id', 'tier')
            )
            p1_tier = tier_map.get(player1.pk)
            p2_tier = tier_map.get(player2.pk)
            if p1_tier is not None and p2_tier is not None and p1_tier != p2_tier:
                raise forms.ValidationError(
                    {'player2': 'This player is not in the same tier to schedule a match.'}
                )

        return cleaned


class ResultEntryForm(forms.Form):
    """
    Dynamic score-entry form. Generates fields for up to (2 * sets_to_win − 1)
    sets based on the season configuration:
      - set{n}_p1 / set{n}_p2  — game counts (left blank = set not played)
      - set{n}_tb_p1 / set{n}_tb_p2  — tiebreak points (shown only for 7-6 sets)
    For the deciding set in 'super' format, set{n}_p1/p2 hold the 10-point
    super-tiebreak scores directly (no separate tiebreak fields).
    """

    def __init__(self, *args, match=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.match = match
        season = match.season
        self.max_sets = season.max_sets_in_match
        is_super_final = season.is_super_final_format

        score_widget_attrs = {
            'inputmode': 'numeric',
            'class': 'form-control score-input',
            'placeholder': '0',
            'style': 'min-height:44px;',
        }

        for i in range(1, self.max_sets + 1):
            is_super = (i == self.max_sets) and is_super_final
            self.fields[f'set{i}_p1'] = forms.IntegerField(
                required=False,
                min_value=0,
                widget=forms.NumberInput(attrs={
                    **score_widget_attrs,
                    'data-set': str(i),
                    'data-player': '1',
                }),
            )
            self.fields[f'set{i}_p2'] = forms.IntegerField(
                required=False,
                min_value=0,
                widget=forms.NumberInput(attrs={
                    **score_widget_attrs,
                    'data-set': str(i),
                    'data-player': '2',
                }),
            )
            if not is_super:
                self.fields[f'set{i}_tb_p1'] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    widget=forms.NumberInput(attrs=score_widget_attrs),
                )
                self.fields[f'set{i}_tb_p2'] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    widget=forms.NumberInput(attrs=score_widget_attrs),
                )

    # ── Per-set score validators ──────────────────────────────────────────

    def _validate_set_score(self, set_num, p1, p2, tb_p1, tb_p2):
        """Return an error string if the set score is illegal, else None."""
        season = self.match.season
        is_deciding = (set_num == self.max_sets)
        is_super = is_deciding and season.is_super_final_format
        is_final_tb = is_deciding and season.is_tiebreak_final_format

        if is_super:
            winner, loser = max(p1, p2), min(p1, p2)
            if winner < 10:
                return f'Set {set_num}: Super tiebreak winner must reach at least 10 points.'
            if winner - loser < 2:
                return f'Set {set_num}: Super tiebreak winner must lead by at least 2 points.'
            return None

        g = season.games_to_win_set

        if is_final_tb:
            if not ((p1 == g + 1 and p2 == g) or (p1 == g and p2 == g + 1)):
                return f'Set {set_num}: The deciding set must end {g+1}-{g} (tiebreak format required).'
            return self._validate_tiebreak_points(set_num, p1, p2, tb_p1, tb_p2)

        # Normal set (or full-format final set)
        if (p1 == g + 1 and p2 == g) or (p1 == g and p2 == g + 1):
            return self._validate_tiebreak_points(set_num, p1, p2, tb_p1, tb_p2)

        # Non-tiebreak set
        if tb_p1 is not None or tb_p2 is not None:
            return f'Set {set_num}: Tiebreak scores should only be entered for {g+1}-{g} sets.'
        winner, loser = max(p1, p2), min(p1, p2)
        if winner < g:
            return f'Set {set_num}: Set winner must win at least {g} games.'
        if winner - loser < 2:
            return f'Set {set_num}: Set winner must lead by at least 2 games.'
        if winner > g + 1 or (winner == g + 1 and loser != g - 1):
            return (
                f'Set {set_num}: Invalid set score '
                f'(valid scores: {g}-0 to {g}-{g-2}, {g+1}-{g-1}, or {g+1}-{g} with tiebreak).'
            )
        return None

    def _validate_tiebreak_points(self, set_num, p1_games, p2_games, tb_p1, tb_p2):
        """Validate tiebreak points for a tiebreak set. Return error string or None."""
        g = self.match.season.games_to_win_set
        if tb_p1 is None or tb_p2 is None:
            return f'Set {set_num}: Tiebreak scores are required for a {g+1}-{g} set.'
        if (p1_games > p2_games) != (tb_p1 > tb_p2):
            return f'Set {set_num}: Tiebreak winner must match the set winner.'
        winner_pts = max(tb_p1, tb_p2)
        if winner_pts < 7:
            return f'Set {set_num}: Tiebreak winner must reach at least 7 points.'
        if winner_pts - min(tb_p1, tb_p2) < 2:
            return f'Set {set_num}: Tiebreak winner must lead by at least 2 points.'
        return None

    # ── Main clean ────────────────────────────────────────────────────────

    def clean(self):
        cleaned = super().clean()
        season = self.match.season
        max_sets = self.max_sets
        is_super_final = season.is_super_final_format

        # Collect set data: (set_num, p1, p2, tb_p1, tb_p2) or None
        all_sets = []
        for i in range(1, max_sets + 1):
            p1 = cleaned.get(f'set{i}_p1')
            p2 = cleaned.get(f'set{i}_p2')
            is_super = (i == max_sets) and is_super_final
            tb_p1 = None if is_super else cleaned.get(f'set{i}_tb_p1')
            tb_p2 = None if is_super else cleaned.get(f'set{i}_tb_p2')

            if p1 is None and p2 is None:
                all_sets.append(None)
            elif p1 is None or p2 is None:
                raise forms.ValidationError(
                    f'Set {i}: both game scores must be provided together.'
                )
            else:
                all_sets.append((i, p1, p2, tb_p1, tb_p2))

        # Find the last played set
        last_idx = next(
            (idx for idx in range(max_sets - 1, -1, -1) if all_sets[idx] is not None),
            None,
        )
        if last_idx is None:
            raise forms.ValidationError('Please enter at least one set score.')

        # No gaps before the last played set
        for idx in range(last_idx):
            if all_sets[idx] is None:
                raise forms.ValidationError(
                    f'Set {idx + 1} score is missing. Please fill sets in order.'
                )

        # Validate each played set and track match progress
        p1_wins = p2_wins = 0
        match_decided_at = None

        for idx in range(last_idx + 1):
            set_data = all_sets[idx]
            if set_data is None:
                continue
            set_num, p1, p2, tb_p1, tb_p2 = set_data

            if match_decided_at is not None:
                raise forms.ValidationError(
                    f'Set {set_num} cannot be played — the match was decided after '
                    f'Set {match_decided_at}.'
                )

            err = self._validate_set_score(set_num, p1, p2, tb_p1, tb_p2)
            if err:
                raise forms.ValidationError(err)

            if p1 > p2:
                p1_wins += 1
            else:
                p2_wins += 1

            if p1_wins == season.sets_to_win or p2_wins == season.sets_to_win:
                match_decided_at = set_num

        if match_decided_at is None:
            raise forms.ValidationError(
                f'The match is incomplete — a player must win {season.sets_to_win} set(s).'
            )

        return cleaned
