from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0010_add_season_display_flag'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(
                    default='TennisLeague',
                    help_text='Displayed in the navbar and page footer.',
                    max_length=100,
                )),
                ('logo', models.TextField(
                    blank=True,
                    help_text='Base64-encoded data URL of the logo image (set via the admin upload field).',
                )),
            ],
            options={
                'verbose_name': 'Site Configuration',
                'verbose_name_plural': 'Site Configuration',
            },
        ),
    ]
