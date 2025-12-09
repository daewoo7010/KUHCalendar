from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, LeaveBalance, LeaveRequest, LeaveApprovalStep, TripRequest, TripReportRecipient

# --- Custom Actions ---
@admin.action(description='[승인] 선택한 휴가 신청 승인 및 연차 차감')
def approve_leaves(modeladmin, request, queryset):
    for leave_request in queryset:
        if leave_request.status == 'approved':
            continue
        leave_request.status = 'approved'
        leave_request.save()
        if leave_request.days and leave_request.days > 0:
            balance, _ = LeaveBalance.objects.get_or_create(user=leave_request.user)
            current_used = balance.used_leave if balance.used_leave else 0
            balance.used_leave = current_used + leave_request.days
            balance.save()

@admin.action(description='[승인] 선택한 출장 신청 승인')
def approve_trips(modeladmin, request, queryset):
    queryset.update(status='approved')

# --- Admin Classes ---

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'department', 'position', 'join_date', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('추가 정보', {'fields': ('department', 'position', 'join_date')}),
    )

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_leave', 'used_leave', 'remaining_leave')
    
    def remaining_leave(self, obj):
        total = obj.total_leave if obj.total_leave else 0
        used = obj.used_leave if obj.used_leave else 0
        return total - used
    remaining_leave.short_description = '잔여 연차'

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'leave_type', 'start_date', 'end_date', 'days', 'status')
    list_filter = ('status', 'leave_type')
    actions = [approve_leaves]

@admin.register(TripRequest)
class TripRequestAdmin(admin.ModelAdmin):
    # 목적 요약과 보고서 요약 모두 표시
    list_display = ('user', 'location', 'purpose_summary', 'start_date', 'end_date', 'status', 'report_preview')
    list_filter = ('status',)
    actions = [approve_trips]
    
    fields = ('user', 'location', 'purpose', 'start_date', 'end_date', 'status', 'report_content')

    def purpose_summary(self, obj):
        return obj.purpose[:20] + "..." if len(obj.purpose) > 20 else obj.purpose
    purpose_summary.short_description = "출장 목적"

    def report_preview(self, obj):
        if not obj.report_content:
            return "-"
        return obj.report_content[:30] + "..." if len(obj.report_content) > 30 else obj.report_content
    report_preview.short_description = "보고서 내용"


@admin.register(LeaveApprovalStep)
class LeaveApprovalStepAdmin(admin.ModelAdmin):
    list_display = ('leave', 'order', 'approver', 'status', 'decided_at')
    list_filter = ('status',)


@admin.register(TripReportRecipient)
class TripReportRecipientAdmin(admin.ModelAdmin):
    list_display = ('user',)