from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Season = apps.get_model('leagues', 'Season')
    for season in Season.objects.all():
        base = slugify(f'{season.name}-{season.year}')
        slug = base
        n = 1
        while Season.objects.filter(slug=slug).exclude(pk=season.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        season.slug = slug
        season.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0006_add_schedule_type_to_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='season',
            name='slug',
            field=models.SlugField(max_length=120, default=''),
            preserve_default=False,
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='season',
            name='slug',
            field=models.SlugField(max_length=120, unique=True),
        ),
    ]
