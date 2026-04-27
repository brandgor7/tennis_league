from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.conf import settings
from django.utils.text import slugify


class SiteConfig(models.Model):
    site_name = models.CharField(
        max_length=100,
        default='TennisLeague',
        help_text='Displayed in the navbar and page footer.',
    )
    logo = models.TextField(
        blank=True,
        help_text='Base64-encoded data URL of the logo image (set via the admin upload field).',
    )
    class Meta:
        verbose_name = 'Site Configuration'
        verbose_name_plural = 'Site Configuration'

    def __str__(self):
        return 'Site Configuration'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def logo_url(self):
        """Return logo only when it is a data URL with an image MIME type."""
        return self.logo if self.logo.startswith('data:image/') else None

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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

    SCHEDULE_SINGLE_DAY = 'single_day'
    SCHEDULE_CONSECUTIVE_DAYS = 'consecutive_days'
    SCHEDULE_WEEKLY = 'weekly'
    SCHEDULE_TYPE_CHOICES = [
        (SCHEDULE_SINGLE_DAY, 'Single day'),
        (SCHEDULE_CONSECUTIVE_DAYS, 'Consecutive days'),
        (SCHEDULE_WEEKLY, 'Weekly'),
    ]

    DISPLAY_ALL = 'all'
    DISPLAY_CURRENT_DAY = 'current_day'
    DISPLAY_CURRENT_WEEK = 'current_week'
    DISPLAY_NEXT_X_DAYS = 'next_x_days'
    DISPLAY_MODE_CHOICES = [
        (DISPLAY_ALL, 'All upcoming matches'),
        (DISPLAY_CURRENT_DAY, 'Current day (+ overdue unplayed)'),
        (DISPLAY_CURRENT_WEEK, 'Current week (+ overdue unplayed)'),
        (DISPLAY_NEXT_X_DAYS, 'Next X days (+ overdue unplayed)'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPCOMING)
    sets_to_win = models.IntegerField(default=2, help_text='2 = best of 3, 3 = best of 5')
    games_to_win_set = models.IntegerField(default=6, help_text='Games needed to win a set (typically 6, sometimes 8)')
    final_set_format = models.CharField(max_length=20, choices=FINAL_SET_CHOICES, default=FINAL_SET_FULL)
    playoff_qualifiers_count = models.IntegerField(default=8)
    walkover_rule = models.CharField(max_length=20, choices=WALKOVER_CHOICES, default=WALKOVER_WINNER)
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default=SCHEDULE_WEEKLY, help_text='How match days are spaced across the season')
    postponement_deadline = models.IntegerField(default=14, help_text='Days allowed to reschedule')
    grace_period_days = models.IntegerField(default=7, help_text='Days after the scheduled date a match can be played without a formal postponement')
    points_for_win = models.IntegerField(default=3)
    points_for_loss = models.IntegerField(default=0)
    points_for_walkover_loss = models.IntegerField(default=0)
    schedule_display_mode = models.CharField(
        max_length=20,
        choices=DISPLAY_MODE_CHOICES,
        default=DISPLAY_ALL,
        help_text='Which upcoming matches to show on the matchups page',
    )
    schedule_display_days = models.IntegerField(
        default=7,
        help_text='Days ahead to show when display mode is "Next X days"',
    )
    playoffs_enabled = models.BooleanField(
        default=True,
        help_text='Show playoff bracket tab and admin playoff actions for this season',
    )
    preseason = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='postseasons',
        help_text=(
            'Attach a previous season here to prevent rematches when generating the schedule — '
            'any matchup that already occurred in the attached season will be skipped.'
        ),
    )
    display = models.BooleanField(
        default=True,
        help_text='Show this season in the dropdown for non-admin users who are not part of this season',
    )
    show_rules = models.BooleanField(
        default=False,
        help_text='Show the Rules page in the navbar for this season.',
    )
    rules_content = models.TextField(
        blank=True,
        help_text='Rules text in Markdown format.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', 'name']

    @property
    def max_sets_in_match(self):
        return 2 * self.sets_to_win - 1

    @property
    def is_super_final_format(self):
        return self.final_set_format == self.FINAL_SET_SUPER

    @property
    def is_tiebreak_final_format(self):
        return self.final_set_format == self.FINAL_SET_TIEBREAK

    def save(self, *args, **kwargs):
        base = slugify(f'{self.name}-{self.year}')
        if not self.slug or not self.slug.startswith(base):
            slug = base
            n = 1
            while Season.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        if self.status == self.STATUS_ACTIVE:
            qs = Season.objects.filter(status=self.STATUS_ACTIVE)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    {'status': 'Only one season can be active at a time.'}
                )
        if self.pk and self.preseason_id == self.pk:
            raise ValidationError(
                {'preseason': 'A season cannot be its own preseason.'}
            )

    @property
    def num_tiers(self):
        return len(self.tiers.all()) or 1

    def tier_name(self, number):
        for tier in self.tiers.all():
            if tier.number == number:
                return tier.name
        return f'Tier {number}'

    def __str__(self):
        return f'{self.name} {self.year}'


class Tier(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='tiers')
    number = models.IntegerField(help_text='1-indexed tier ordering')
    name = models.CharField(max_length=50, help_text='Display name (e.g. Premier, Division 1)')

    class Meta:
        unique_together = [('season', 'number')]
        ordering = ['number']

    def __str__(self):
        return f'{self.name} — {self.season}'


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
