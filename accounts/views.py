from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from matches.models import Match


@login_required
def profile(request):
    user = request.user
    matches_qs = (
        Match.objects
        .filter(
            Q(player1=user) | Q(player2=user),
            status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER],
        )
        .select_related('player1', 'player2', 'winner', 'season')
        .order_by('-played_date', '-created_at')
    )

    history = []
    wins = 0
    losses = 0
    for m in matches_qs:
        opponent = m.player2 if m.player1_id == user.pk else m.player1
        if m.winner_id == user.pk:
            result = 'W'
            wins += 1
        elif m.winner_id is not None:
            result = 'L'
            losses += 1
        else:
            result = '—'
        history.append({'match': m, 'opponent': opponent, 'result': result})

    return render(request, 'accounts/profile.html', {
        'history': history,
        'wins': wins,
        'losses': losses,
    })
