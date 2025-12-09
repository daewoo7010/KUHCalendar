from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from datetime import timedelta, date


class CustomUser(AbstractUser):
    department = models.CharField(max_length=50, blank=True, null=True)
    position = models.CharField(max_length=50, blank=True, null=True)
    join_date = models.DateField(null=True, blank=True)


class LeaveBalance(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='leave_balance')
    total_leave = models.FloatField(default=15)
    used_leave = models.FloatField(default=0)

    @property
    def remaining_leave(self):
        return self.total_leave - self.used_leave

    def __str__(self):
        return f"{self.user.username}의 연차"


class LeaveRequest(models.Model):
    LEAVE_TYPES = [('연차', '연차'), ('반차', '반차'), ('병가', '병가'), ('기타', '기타')]
    STATUS_CHOICES = [('pending', '대기'), ('approved', '승인'), ('rejected', '반려')]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=10, choices=LEAVE_TYPES)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    days = models.FloatField(null=True, blank=True, help_text="자동 계산된 휴가 일수(주말 제외)")

    def save(self, *args, **kwargs):
        # 휴가 일수 자동 계산 로직 (주말 제외)
        if self.start_date and self.end_date:
            if self.leave_type == '반차':
                self.days = 0.5
            else:
                day_count = 0
                current_date = self.start_date
                while current_date <= self.end_date:
                    # 5=토요일, 6=일요일 (주말 제외)
                    if current_date.weekday() < 5:
                        day_count += 1
                    current_date += timedelta(days=1)
                self.days = float(day_count)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.leave_type} ({self.start_date})"


class LeaveApprovalStep(models.Model):
    STATUS_CHOICES = [('pending', '대기'), ('approved', '승인'), ('rejected', '반려')]

    leave = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name='approval_steps')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_approvals')
    order = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['leave', 'order']
        unique_together = ('leave', 'order')

    def __str__(self):
        return f"{self.leave_id} step {self.order} - {self.approver} ({self.status})"


class TripRequest(models.Model):
    STATUS_CHOICES = [('pending', '대기'), ('approved', '승인'), ('rejected', '반려')]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='trip_participations', blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    location = models.CharField(max_length=100)
    purpose = models.TextField()
    report_content = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    all_day = models.BooleanField(default=False)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("종료일은 시작일보다 빠를 수 없습니다.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - 출장 ({self.location})"


class TripReportRecipient(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trip_report_recipient')

    def __str__(self):
        return f"출장 보고 수신: {self.user.username}"