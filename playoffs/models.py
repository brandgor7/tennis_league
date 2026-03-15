from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from matches.models import PLAYOFF_ROUND_CHOICES, Match


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


@receiver(post_save, sender=Match)
def advance_playoff_winner(sender, instance, **kwargs):
    """When a playoff match finishes, place the winner in the next round's match."""
    if instance.status not in (Match.STATUS_COMPLETED, Match.STATUS_WALKOVER):
        return
    if not instance.winner_id:
        return
    try:
        slot = instance.playoff_slot
    except PlayoffSlot.DoesNotExist:
        return
    if not slot.next_slot:
        return

    next_match = slot.next_slot.match
    prev_slots = list(slot.next_slot.previous_slots.order_by('bracket_position'))
    if prev_slots and slot == prev_slots[0]:
        next_match.player1 = instance.winner
    else:
        next_match.player2 = instance.winner
    next_match.save(update_fields=['player1', 'player2'])
