from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0009_personalevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='feed_token',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
