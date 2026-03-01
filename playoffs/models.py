from django.db import models
from django.conf import settings
from matches.models import PLAYOFF_ROUND_CHOICES


class PlayoffBracket(models.Model):
    season = models.ForeignKey('leagues.Season', on_delete=models.CASCADE, related_name='playoff_brackets')
    tier = models.IntegerField(default=1, help_text='Which tier this bracket is for (1-indexed)')
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='brackets_generated')

    class Meta:
        unique_together = [('season', 'tier')]

    def __str__(self):
        return f'Playoff Bracket — {self.season} (Tier {self.tier})'


class PlayoffSlot(models.Model):
    bracket = models.ForeignKey(PlayoffBracket, on_delete=models.CASCADE, related_name='slots')
    match = models.OneToOneField('matches.Match', on_delete=models.CASCADE, related_name='playoff_slot')
    bracket_position = models.IntegerField(help_text='1-indexed position in the bracket')
    round = models.CharField(max_length=20, choices=PLAYOFF_ROUND_CHOICES)
    next_slot = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='previous_slots',
        help_text="Winner of this slot advances to next_slot's match",
    )

    class Meta:
        ordering = ['bracket_position']

    def __str__(self):
        return f'{self.bracket} — {self.get_round_display()} pos {self.bracket_position}'
