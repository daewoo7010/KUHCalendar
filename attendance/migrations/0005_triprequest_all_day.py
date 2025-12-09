from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_alter_triprequest_dates_to_datetime'),
    ]

    operations = [
        migrations.AddField(
            model_name='triprequest',
            name='all_day',
            field=models.BooleanField(default=False),
        ),
    ]
