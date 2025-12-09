from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_tripreportrecipient_leaveapprovalstep'),
    ]

    operations = [
        migrations.AlterField(
            model_name='triprequest',
            name='start_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='triprequest',
            name='end_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
