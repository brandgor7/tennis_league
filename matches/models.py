from django.db import models
from django.db.models import F, Q
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
    STATUS_BYE = 'bye'
    STATUS_POSTPONED = 'postponed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_PENDING, 'Pending Confirmation'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_WALKOVER, 'Walkover'),
        (STATUS_BYE, 'Bye'),
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
    external_player1_name = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Set instead of player1 when this side is a player not registered in the system.',
    )
    external_player2_name = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Set instead of player2 when this side is a player not registered in the system.',
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
    winner_is_external = models.BooleanField(
        default=False,
        help_text='Set when the external player (rather than winner) won the match.',
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

    @staticmethod
    def decided_players_q():
        """Q object matching matches where both sides are filled in (real or external)."""
        return (
            (Q(player1__isnull=False) | ~Q(external_player1_name='')) &
            (Q(player2__isnull=False) | ~Q(external_player2_name=''))
        )

    def clean(self):
        errors = {}
        if self.player1_id and self.player2_id and self.player1_id == self.player2_id:
            errors['player2'] = 'A player cannot be matched against themselves.'
        if self.player1_id and self.external_player1_name:
            errors['external_player1_name'] = 'Cannot set both a registered player and an external player name for Player 1.'
        if self.player2_id and self.external_player2_name:
            errors['external_player2_name'] = 'Cannot set both a registered player and an external player name for Player 2.'
        if self.external_player1_name and self.external_player2_name:
            errors['external_player2_name'] = 'A match cannot have external players on both sides.'
        if self.external_player1_name or self.external_player2_name:
            if self.round != self.ROUND_REGULAR:
                errors['round'] = 'External players are only allowed in regular season matches.'
            if self.season_id and not self.season.allow_external_players:
                errors['__all__'] = 'This season does not allow matches with external players.'
        if self.winner_is_external and not (self.external_player1_name or self.external_player2_name):
            errors['winner_is_external'] = 'There is no external player on this match to mark as the winner.'
        if self.winner_id and self.winner_id not in (self.player1_id, self.player2_id):
            errors['winner'] = 'Winner must be one of the two players in this match.'
        if self.winner_id and self.winner_is_external:
            errors['winner'] = 'Cannot set both a winner and mark the external player as the winner.'
        if errors:
            raise ValidationError(errors)

    @property
    def has_external_player(self):
        return bool(self.external_player1_name or self.external_player2_name)

    @property
    def both_sides_decided(self):
        """True once both slots are filled in, whether by a real player or an external name.

        False for future playoff-bracket rounds where both players are still TBD.
        """
        p1_decided = self.player1_id is not None or bool(self.external_player1_name)
        p2_decided = self.player2_id is not None or bool(self.external_player2_name)
        return p1_decided and p2_decided

    def set_winner_side(self, player1_won):
        """Set the winner given which side (player1 or player2) won.

        Handles the external-player case, where the winning side has no User
        to point `winner` at — `winner_is_external` is set instead.
        """
        if player1_won:
            self.winner = self.player1
            self.winner_is_external = self.player1_id is None
        else:
            self.winner = self.player2
            self.winner_is_external = self.player2_id is None

    @property
    def player1_display_name(self):
        if self.player1_id:
            return self.player1.get_full_name() or self.player1.username
        return self.external_player1_name or 'TBD'

    @property
    def player2_display_name(self):
        if self.player2_id:
            return self.player2.get_full_name() or self.player2.username
        return self.external_player2_name or 'TBD'

    @property
    def winner_display_name(self):
        if self.winner_is_external:
            return self.external_player1_name or self.external_player2_name
        if self.winner_id:
            return self.winner.get_full_name() or self.winner.username
        return ''

    @property
    def player1_is_winner(self):
        if self.winner_id:
            return self.winner_id == self.player1_id
        return self.winner_is_external and bool(self.external_player1_name)

    @property
    def player2_is_winner(self):
        if self.winner_id:
            return self.winner_id == self.player2_id
        return self.winner_is_external and bool(self.external_player2_name)

    def __str__(self):
        return f'{self.player1_display_name} vs {self.player2_display_name} ({self.season})'


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
