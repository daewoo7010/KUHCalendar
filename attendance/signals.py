from django.conf import settings
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import LeaveBalance


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_leave_balance(sender, instance, created, **kwargs):
    if created:
        LeaveBalance.objects.create(user=instance, total_leave=15, used_leave=0)


ADMIN_GROUP_NAME = '관리자'


def _ensure_staff_for_admin_group(user):
    # Grant staff if user is in 관리자 그룹; do not remove staff flag automatically
    try:
        if user.groups.filter(name=ADMIN_GROUP_NAME).exists() and not user.is_staff:
            user.is_staff = True
            user.save(update_fields=['is_staff'])
    except Exception:
        # Fail silently to avoid breaking signal chain
        pass


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_staff_on_user_save(sender, instance, **kwargs):
    _ensure_staff_for_admin_group(instance)


@receiver(m2m_changed, sender=get_user_model().groups.through)
def ensure_staff_on_group_change(sender, instance, action, **kwargs):
    if action in {'post_add', 'post_remove', 'post_clear'}:
        _ensure_staff_for_admin_group(instance)
