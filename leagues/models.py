from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.conf import settings


class Season(models.Model):
    STATUS_UPCOMING = 'upcoming'
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_UPCOMING, 'Upcoming'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    FINAL_SET_FULL = 'full'
    FINAL_SET_TIEBREAK = 'tiebreak'
    FINAL_SET_SUPER = 'super'
    FINAL_SET_CHOICES = [
        (FINAL_SET_FULL, 'Full Set'),
        (FINAL_SET_TIEBREAK, 'Tiebreak'),
        (FINAL_SET_SUPER, 'Super Tiebreak'),
    ]

    WALKOVER_WINNER = 'winner'
    WALKOVER_SPLIT = 'split'
    WALKOVER_NONE = 'none'
    WALKOVER_CHOICES = [
        (WALKOVER_WINNER, 'Winner gets all points'),
        (WALKOVER_SPLIT, 'Winner gets win points, loser gets walkover-loss points'),
        (WALKOVER_NONE, 'No points awarded'),
    ]

    name = models.CharField(max_length=100)
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPCOMING)
    num_tiers = models.IntegerField(default=1, help_text='Number of competitive tiers in this season')
    sets_to_win = models.IntegerField(default=2, help_text='2 = best of 3, 3 = best of 5')
    final_set_format = models.CharField(max_length=20, choices=FINAL_SET_CHOICES, default=FINAL_SET_FULL)
    playoff_qualifiers_count = models.IntegerField(default=8)
    walkover_rule = models.CharField(max_length=20, choices=WALKOVER_CHOICES, default=WALKOVER_WINNER)
    postponement_deadline = models.IntegerField(default=14, help_text='Days allowed to reschedule')
    points_for_win = models.IntegerField(default=3)
    points_for_loss = models.IntegerField(default=0)
    points_for_walkover_loss = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', 'name']

    def clean(self):
        if self.status == self.STATUS_ACTIVE:
            qs = Season.objects.filter(status=self.STATUS_ACTIVE)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    {'status': 'Only one season can be active at a time.'}
                )

    def __str__(self):
        return f'{self.name} ({self.year})'


class SeasonPlayer(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='season_players')
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='season_players')
    tier = models.IntegerField(default=1, help_text='1-indexed tier number for this player in this season')
    seed = models.IntegerField(null=True, blank=True, help_text='Initial seeding for playoffs')
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('season', 'player')]
        ordering = [F('seed').asc(nulls_last=True), 'player__last_name', 'player__first_name']

    def __str__(self):
        return f'{self.player} — {self.season}'
