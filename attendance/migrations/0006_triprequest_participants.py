# Generated manually for participants field
from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_triprequest_all_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='triprequest',
            name='participants',
            field=models.ManyToManyField(blank=True, related_name='trip_participations', to=settings.AUTH_USER_MODEL),
        ),
    ]
