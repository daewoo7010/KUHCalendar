from django import template
from attendance.models import TripReportRecipient

register = template.Library()


@register.filter
def has_group(user, group_name):
    """Return True if the user belongs to the given group name."""
    if not user or not hasattr(user, "groups"):
        return False
    return user.groups.filter(name=group_name).exists()


@register.filter
def is_trip_recipient(user):
    if not user or not user.is_authenticated:
        return False
    return TripReportRecipient.objects.filter(user=user).exists()
