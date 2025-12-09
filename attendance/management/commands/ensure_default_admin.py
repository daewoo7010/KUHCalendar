import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Ensure a default admin user exists based on env vars."

    def handle(self, *args, **options):
        username = os.environ.get("DEFAULT_ADMIN_USERNAME")
        password = os.environ.get("DEFAULT_ADMIN_PASSWORD")
        email = os.environ.get("DEFAULT_ADMIN_EMAIL", "")

        if not username or not password:
            self.stdout.write(self.style.WARNING("Skipping default admin creation: env vars not set."))
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        updated = False

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created default admin '{username}'."))
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

        if not user.check_password(password):
            user.set_password(password)
            updated = True

        if updated:
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Updated default admin '{username}'."))
        else:
            self.stdout.write(f"Default admin '{username}' already up-to-date.")
