from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0011_siteconfig'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='siteconfig',
            name='logo_svg',
        ),
        migrations.AddField(
            model_name='siteconfig',
            name='logo',
            field=models.TextField(
                blank=True,
                help_text='Base64-encoded data URL of the logo image (set via the admin upload field).',
            ),
        ),
    ]
