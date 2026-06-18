from django.db import migrations, models
from django.utils.text import slugify


def populate_team_slugs(apps, schema_editor):
    Team = apps.get_model('leagues', 'Team')
    Season = apps.get_model('leagues', 'Season')

    season_use_team_name = {s.pk: s.use_team_name for s in Season.objects.all()}
    seen = {}  # (season_id, slug) -> True

    for team in Team.objects.prefetch_related('members').order_by('season_id', 'pk'):
        use_name = team.name and season_use_team_name.get(team.season_id, False)
        if use_name:
            base = slugify(team.name)
        else:
            members = list(team.members.order_by('last_name', 'first_name'))
            last_names = [m.last_name or m.username for m in members]
            base = slugify('-'.join(last_names)) if last_names else 'team'

        base = base or 'team'
        slug = base
        n = 1
        while (team.season_id, slug) in seen:
            slug = f'{base}-{n}'
            n += 1
        seen[(team.season_id, slug)] = True
        Team.objects.filter(pk=team.pk).update(slug=slug)


class Migration(migrations.Migration):
    dependencies = [
        ('leagues', '0023_create_teams_from_season_players'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='slug',
            field=models.SlugField(max_length=120, blank=True),
        ),
        migrations.RunPython(populate_team_slugs, migrations.RunPython.noop),
    ]
