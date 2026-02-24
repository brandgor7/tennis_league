from django.db import models
from django.conf import settings


class PlayoffBracket(models.Model):
    season = models.OneToOneField('leagues.Season', on_delete=models.CASCADE, related_name='playoff_bracket')
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='brackets_generated')

    def __str__(self):
        return f'Playoff Bracket — {self.season}'


class PlayoffSlot(models.Model):
    ROUND_R32 = 'r32'
    ROUND_R16 = 'r16'
    ROUND_QF = 'qf'
    ROUND_SF = 'sf'
    ROUND_FINAL = 'f'
    ROUND_CHOICES = [
        (ROUND_R32, 'Round of 32'),
        (ROUND_R16, 'Round of 16'),
        (ROUND_QF, 'Quarterfinal'),
        (ROUND_SF, 'Semifinal'),
        (ROUND_FINAL, 'Final'),
    ]

    bracket = models.ForeignKey(PlayoffBracket, on_delete=models.CASCADE, related_name='slots')
    match = models.OneToOneField('matches.Match', on_delete=models.CASCADE, related_name='playoff_slot')
    bracket_position = models.IntegerField(help_text='1-indexed position in the bracket')
    round = models.CharField(max_length=20, choices=ROUND_CHOICES)
    next_slot = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='previous_slots',
        help_text='Winner of this slot advances to next_slot\'s match',
    )

    class Meta:
        ordering = ['round', 'bracket_position']

    def __str__(self):
        return f'{self.bracket} — {self.get_round_display()} pos {self.bracket_position}'
