from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('leagues', '0014_season_playoffs_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteconfig',
            name='show_rules',
            field=models.BooleanField(default=False, help_text='Show the Rules page in the navbar.'),
        ),
        migrations.AddField(
            model_name='siteconfig',
            name='rules_content',
            field=models.TextField(blank=True, help_text='Rules text in Markdown format.'),
        ),
    ]
