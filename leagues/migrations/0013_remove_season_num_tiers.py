from django.db import migrations


def backfill_tiers(apps, schema_editor):
    Season = apps.get_model('leagues', 'Season')
    Tier = apps.get_model('leagues', 'Tier')
    for season in Season.objects.filter(num_tiers__gte=2):
        for number in range(1, season.num_tiers + 1):
            Tier.objects.get_or_create(
                season=season,
                number=number,
                defaults={'name': f'Tier {number}'},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0012_add_tier_model'),
    ]

    operations = [
        migrations.RunPython(backfill_tiers, migrations.RunPython.noop),
        migrations.RemoveField(model_name='season', name='num_tiers'),
    ]
