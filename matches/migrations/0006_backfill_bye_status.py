from django.db import migrations
from django.db.models import Q


def backfill_bye_status(apps, schema_editor):
    Match = apps.get_model('matches', 'Match')
    Match.objects.filter(
        status='walkover',
        winner__isnull=False,
    ).filter(
        Q(player1__isnull=True) | Q(player2__isnull=True),
    ).update(status='bye')


class Migration(migrations.Migration):

    dependencies = [
        ('matches', '0005_add_bye_status'),
    ]

    operations = [
        migrations.RunPython(backfill_bye_status, migrations.RunPython.noop),
    ]
