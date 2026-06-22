from datetime import date

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def season():
    from leagues.models import Season, Tier
    s = Season.objects.create(name="Visual Test Season", year=2025, status="active")
    Tier.objects.create(season=s, number=1, name="Division 1")
    return s


@pytest.fixture
def players(season):
    from leagues.models import SeasonPlayer
    names = [("Alice", "Adams"), ("Bob", "Brown"), ("Carol", "Clark"), ("Dan", "Davis")]
    users = []
    for i, (first, last) in enumerate(names, start=1):
        u = User.objects.create_user(
            username=f"visual_player{i}",
            first_name=first,
            last_name=last,
            password="testpass",
        )
        SeasonPlayer.objects.create(season=season, player=u, tier=1)
        users.append(u)
    return users


@pytest.fixture
def completed_matches(season, players):
    from matches.models import Match, MatchSet
    p = players
    pairs = [(p[0], p[1], 3), (p[2], p[3], 1), (p[0], p[2], 5), (p[1], p[3], 7)]
    for p1, p2, day in pairs:
        m = Match.objects.create(
            season=season,
            player1=p1,
            player2=p2,
            tier=1,
            status="completed",
            winner=p1,
            played_date=date(2025, 3, day),
        )
        MatchSet.objects.create(match=m, set_number=1, player1_games=6, player2_games=3)
        MatchSet.objects.create(match=m, set_number=2, player1_games=6, player2_games=4)


@pytest.fixture
def scheduled_matches(season, players):
    from matches.models import Match
    p = players
    Match.objects.create(
        season=season, player1=p[0], player2=p[3], tier=1,
        status="scheduled", scheduled_date=date(2025, 4, 10),
    )
    Match.objects.create(
        season=season, player1=p[1], player2=p[2], tier=1,
        status="scheduled", scheduled_date=date(2025, 4, 17),
    )
