from django.db import models
from django.conf import settings


class Match(models.Model):
    ROUND_REGULAR = 'regular'
    ROUND_R32 = 'r32'
    ROUND_R16 = 'r16'
    ROUND_QF = 'qf'
    ROUND_SF = 'sf'
    ROUND_FINAL = 'f'
    ROUND_CHOICES = [
        (ROUND_REGULAR, 'Regular Season'),
        (ROUND_R32, 'Round of 32'),
        (ROUND_R16, 'Round of 16'),
        (ROUND_QF, 'Quarterfinal'),
        (ROUND_SF, 'Semifinal'),
        (ROUND_FINAL, 'Final'),
    ]

    STATUS_SCHEDULED = 'scheduled'
    STATUS_PENDING = 'pending_confirmation'
    STATUS_COMPLETED = 'completed'
    STATUS_WALKOVER = 'walkover'
    STATUS_POSTPONED = 'postponed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_PENDING, 'Pending Confirmation'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_WALKOVER, 'Walkover'),
        (STATUS_POSTPONED, 'Postponed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    season = models.ForeignKey('leagues.Season', on_delete=models.CASCADE, related_name='matches')
    player1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='matches_as_player1')
    player2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='matches_as_player2')
    round = models.CharField(max_length=20, choices=ROUND_CHOICES, default=ROUND_REGULAR)
    scheduled_date = models.DateField(null=True, blank=True)
    played_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='matches_won',
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='matches_entered',
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='matches_confirmed',
    )
    walkover_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_date', 'created_at']
        verbose_name_plural = 'matches'

    def __str__(self):
        return f'{self.player1} vs {self.player2} ({self.season})'


class MatchSet(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='sets')
    set_number = models.IntegerField()
    player1_games = models.IntegerField()
    player2_games = models.IntegerField()
    tiebreak_player1_points = models.IntegerField(null=True, blank=True)
    tiebreak_player2_points = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = [('match', 'set_number')]
        ordering = ['set_number']

    def __str__(self):
        return f'{self.match} — Set {self.set_number}: {self.player1_games}-{self.player2_games}'
