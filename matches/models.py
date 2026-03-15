from django.db import models
from django.db.models import F
from django.conf import settings
from django.core.exceptions import ValidationError


PLAYOFF_ROUND_CHOICES = [
    ('r32', 'Round of 32'),
    ('r16', 'Round of 16'),
    ('qf', 'Quarterfinal'),
    ('sf', 'Semifinal'),
    ('f', 'Final'),
]


class Match(models.Model):
    ROUND_REGULAR = 'regular'
    ROUND_R32 = 'r32'
    ROUND_R16 = 'r16'
    ROUND_QF = 'qf'
    ROUND_SF = 'sf'
    ROUND_FINAL = 'f'
    ROUND_CHOICES = [('regular', 'Regular Season')] + PLAYOFF_ROUND_CHOICES

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
    player1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='matches_as_player1',
    )
    player2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='matches_as_player2',
    )
    tier = models.IntegerField(null=True, blank=True, help_text='Tier this match belongs to; set from players\' tier at match creation')
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
    walkover_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [F('scheduled_date').asc(nulls_last=True), 'created_at']
        verbose_name_plural = 'matches'

    def clean(self):
        errors = {}
        if self.player1_id and self.player2_id and self.player1_id == self.player2_id:
            errors['player2'] = 'A player cannot be matched against themselves.'
        if self.winner_id and self.winner_id not in (self.player1_id, self.player2_id):
            errors['winner'] = 'Winner must be one of the two players in this match.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.player1} vs {self.player2} ({self.season})'


class MatchSet(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='sets')
    set_number = models.PositiveSmallIntegerField()
    player1_games = models.PositiveSmallIntegerField()
    player2_games = models.PositiveSmallIntegerField()
    tiebreak_player1_points = models.PositiveSmallIntegerField(null=True, blank=True)
    tiebreak_player2_points = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [('match', 'set_number')]
        ordering = ['set_number']

    def clean(self):
        tb1_set = self.tiebreak_player1_points is not None
        tb2_set = self.tiebreak_player2_points is not None
        if tb1_set != tb2_set:
            raise ValidationError('Both tiebreak point fields must be set together, or both left empty.')

    def __str__(self):
        return f'{self.match} — Set {self.set_number}: {self.player1_games}-{self.player2_games}'
