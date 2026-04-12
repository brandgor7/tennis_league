from django import forms
from .models import Season


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = [
            'name',
            'year',
            'status',
            'schedule_type',
            'sets_to_win',
            'final_set_format',
            'playoff_qualifiers_count',
            'walkover_rule',
            'postponement_deadline',
            'points_for_win',
            'points_for_loss',
            'points_for_walkover_loss',
        ]
        widgets = {
            'sets_to_win': forms.NumberInput(attrs={'min': 1}),
        }
