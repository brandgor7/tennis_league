from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0017_move_rules_to_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='season',
            name='win_by_two',
            field=models.BooleanField(
                default=True,
                help_text='Require the winner to lead by at least 2 games to win a set. Disable to allow scores like 6–5.',
            ),
        ),
    ]
