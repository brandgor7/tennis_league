from django.db import migrations


def _migrate_data(SeasonPlayer, Team, Match):
    """
    Pass 1: create a single-member Team for every SeasonPlayer.
    Pass 2: populate team1/team2/winning_team on every Match that has player FKs set.
    """
    team_map = {}  # (player_id, season_id) -> Team instance
    for sp in SeasonPlayer.objects.all():
        team = Team.objects.create(
            season_id=sp.season_id,
            tier=sp.tier,
            seed=sp.seed,
            is_active=sp.is_active,
        )
        team.members.add(sp.player_id)
        team_map[(sp.player_id, sp.season_id)] = team

    to_update = []
    for match in Match.objects.filter(player1_id__isnull=False):
        t1 = team_map.get((match.player1_id, match.season_id))
        t2 = team_map.get((match.player2_id, match.season_id)) if match.player2_id else None
        tw = team_map.get((match.winner_id, match.season_id)) if match.winner_id else None
        if t1 or t2 or tw:
            match.team1_id = t1.pk if t1 else None
            match.team2_id = t2.pk if t2 else None
            match.winning_team_id = tw.pk if tw else None
            to_update.append(match)

    if to_update:
        Match.objects.bulk_update(to_update, ['team1_id', 'team2_id', 'winning_team_id'])


def create_teams_from_season_players(apps, schema_editor):
    _migrate_data(
        apps.get_model('leagues', 'SeasonPlayer'),
        apps.get_model('leagues', 'Team'),
        apps.get_model('matches', 'Match'),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('leagues', '0022_season_team_config_and_team_model'),
        ('matches', '0005_match_team_fks'),
    ]

    operations = [
        migrations.RunPython(
            create_teams_from_season_players,
            migrations.RunPython.noop,
        ),
    ]
