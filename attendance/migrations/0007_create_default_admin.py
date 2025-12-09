from django.db import migrations


def create_default_admin(apps, schema_editor):
    """Create a default admin user from env vars if provided."""
    import os

    User = apps.get_model('attendance', 'CustomUser')
    username = os.environ.get('DEFAULT_ADMIN_USERNAME')
    password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
    email = os.environ.get('DEFAULT_ADMIN_EMAIL', '')

    if not username or not password:
        print("Skipping default admin creation: DEFAULT_ADMIN_USERNAME or DEFAULT_ADMIN_PASSWORD not set.")
        return

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'is_staff': True,
            'is_superuser': True,
        },
    )

    updated = False

    if created:
        user.set_password(password)
        user.save()
        return

    if email and user.email != email:
        user.email = email
        updated = True

    if not user.is_staff:
        user.is_staff = True
        updated = True

    if not user.is_superuser:
        user.is_superuser = True
        updated = True

    try:
        if not user.check_password(password):
            user.set_password(password)
            updated = True
    except Exception:
        user.set_password(password)
        updated = True

    if updated:
        user.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0006_triprequest_participants'),
    ]

    operations = [
        migrations.RunPython(create_default_admin, noop_reverse),
    ]
