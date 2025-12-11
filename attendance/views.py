import json
import math
from datetime import timedelta, date

from django.db import models

from django.conf import settings
from django.db.models import Q, Sum

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from .forms import LeaveForm, SignUpForm, TripForm, TripReportForm, MeetingForm, PersonalEventForm
from .models import LeaveApprovalStep, LeaveBalance, LeaveRequest, TripReportRecipient, TripRequest, Meeting, PersonalEvent

ADMIN_GROUP = '관리자'
ROLE_GROUPS = ['관리자', '휴가 결재권자', '출장 결재권자', '경영관리부']


def _user_in_groups(user, group_names):
    return user.is_authenticated and user.groups.filter(name__in=group_names).exists()


def _is_trip_recipient(user):
    if not user or not user.is_authenticated:
        return False
    return TripReportRecipient.objects.filter(user=user).exists()


def _normalize_all_day_event(event_obj):
    """Ensure all-day events span full local days and times are aligned."""
    if getattr(event_obj, 'all_day', False) and event_obj.start_date and event_obj.end_date:
        tz = timezone.get_current_timezone()
        start_date = timezone.localdate(event_obj.start_date)
        end_date = timezone.localdate(event_obj.end_date)
        event_obj.start_date = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()), tz)
        event_obj.end_date = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time().replace(microsecond=0)), tz)


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    first_next = date(year, month + 1, 1)
    return (first_next - timedelta(days=1)).day


def _month_anchor(year: int, month: int, join_day: int) -> date:
    # Accrual assumed when the month reaches the join_day (or last day if shorter).
    day = min(join_day, _last_day_of_month(year, month))
    return date(year, month, day)


def _completed_months(start_date: date, limit_date: date) -> int:
    """Full months completed between start_date and limit_date (start month counts after full month lapses)."""
    if limit_date < start_date:
        return 0
    months = (limit_date.year - start_date.year) * 12 + (limit_date.month - start_date.month)
    if limit_date.day < start_date.day:
        months -= 1
    return max(months, 0)


def _service_year(join_date: date, today: date) -> int:
    """Return 1-based service year, capped at 0 for pre-join."""
    if today < join_date:
        return 0
    months = (today.year - join_date.year) * 12 + (today.month - join_date.month)
    if today.day < join_date.day:
        months -= 1
    return (months // 12) + 1


def _service_year_end(join_date: date, service_year: int) -> date:
    """End date (inclusive) of the given service year, month before anniversary."""
    if service_year < 1:
        return join_date
    # Anniversary month for the service year
    start_year = join_date.year + (service_year - 1)
    ann_month = join_date.month
    if ann_month == 1:
        end_year = start_year
        end_month = 12
    else:
        end_year = start_year + 1
        end_month = ann_month - 1
    return date(end_year, end_month, _last_day_of_month(end_year, end_month))


def _current_leave_segment(join_date: date, today: date):
    """Return current leave segment info based on hire date."""
    if not join_date or join_date > today:
        return None

    first_anniv = join_date.replace(year=join_date.year + 1)
    # Normalize anniversary day for shorter months
    first_anniv = date(first_anniv.year, first_anniv.month, min(first_anniv.day, _last_day_of_month(first_anniv.year, first_anniv.month)))
    first_year_end = first_anniv - timedelta(days=1)

    # Year 1: from join through day before 1st anniversary
    if today <= first_year_end:
        return {
            'type': 'year1_monthly',
            'start': join_date,
            'end': first_year_end,
            'start_month': join_date.month,
        }

    # Year 2 (partial): from anniversary to Dec 31 of anniversary year
    if today.year == first_anniv.year:
        return {
            'type': 'year2_partial_monthly',
            'start': first_anniv,
            'end': date(first_anniv.year, 12, 31),
            'start_month': first_anniv.month,
        }

    # Year 3 (first full calendar year after anniversary): prorated calendar year with rounding
    if today.year == first_anniv.year + 1:
        return {
            'type': 'year3_prorated_calendar',
            'start': date(today.year, 1, 1),
            'end': date(today.year, 12, 31),
            'round_half_up': True,
        }

    # Year 4+ : calendar-year annual grant (15 + (service_year-3))
    service_year = (today.year - join_date.year) + 1
    return {
        'type': 'annual',
        'start': date(today.year, 1, 1),
        'end': date(today.year, 12, 31),
        'annual_days': 15 + (service_year - 3),
        'round_half_up': False,
    }


def _calculate_earned_leave(join_date: date, today: date, segment=None) -> int:
    """Compute earned leave for the current segment."""
    if not join_date or join_date > today:
        return 0

    seg = segment or _current_leave_segment(join_date, today)
    if not seg:
        return 0

    seg_type = seg['type']

    if seg_type in ('year1_monthly', 'year2_partial_monthly'):
        limit_date = min(today, seg['end'])
        return _completed_months(seg['start'], limit_date)

    if seg_type == 'year3_prorated_calendar':
        days_employed = (today - seg['start']).days + 1
        accrued = (days_employed / 365) * 15
        return _round_half_up(accrued) if seg.get('round_half_up') else math.floor(accrued)

    if seg_type == 'annual':
        if today < seg['start']:
            return 0
        return seg['annual_days']

    return 0


def _calculate_used_leave(user, segment) -> float:
    """Sum approved leave days within current segment window."""
    if not segment:
        return 0.0
    start = segment['start']
    end = segment['end']
    return float(
        LeaveRequest.objects.filter(user=user, status='approved', start_date__gte=start, start_date__lte=end)
        .exclude(days__isnull=True)
        .aggregate(Sum('days'))['days__sum'] or 0
    )


def _leave_summary_for_user(user) -> dict:
    today = timezone.localdate()
    join_dt = getattr(user, 'join_date', None)
    segment = _current_leave_segment(join_dt, today)
    earned = _calculate_earned_leave(join_dt, today, segment) if segment else 0
    used = _calculate_used_leave(user, segment)
    remaining = earned - used
    usage_rate = (used / earned * 100) if earned > 0 else 0
    reset_date = segment['end'] if segment else None
    return {
        'earned': earned,
        'used': used,
        'remaining': remaining,
        'missing_join_date': join_dt is None,
        'join_date': join_dt,
        'usage_rate': usage_rate,
        'reset_date': reset_date,
    }


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 첫 가입자라면 자동으로 관리자 권한 부여
            User = get_user_model()
            if not User.objects.filter(is_superuser=True).exists():
                user.is_superuser = True
                user.is_staff = True
                user.save(update_fields=['is_superuser', 'is_staff'])
                admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
                user.groups.add(admin_group)
            login(request, user)
            messages.success(request, '회원가입이 완료되었습니다.')
            return redirect('dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


def password_reset_request(request):
    User = get_user_model()

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        name = request.POST.get('name', '').strip()
        target = User.objects.filter(email=email).filter(Q(username=name) | Q(first_name=name) | Q(last_name=name)).first()

        if not target:
            messages.error(request, '일치하는 사용자 정보를 찾을 수 없습니다.')
        else:
            temp_pw = get_random_string(10)
            target.set_password(temp_pw)
            target.save(update_fields=['password'])

            subject = '[근태 시스템] 임시 비밀번호 안내'
            body = (
                f"{target.username}님 안녕하세요.\n\n"
                f"요청하신 임시 비밀번호는 아래와 같습니다.\n"
                f"임시 비밀번호: {temp_pw}\n\n"
                "보안을 위해 로그인 후 비밀번호를 변경해주세요."
            )

            from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@example.com'
            try:
                send_mail(subject, body, from_addr, [email], fail_silently=False)
                messages.success(request, '임시 비밀번호를 이메일로 보냈습니다. 메일함을 확인해주세요.')
                return redirect('login')
            except Exception:
                messages.warning(request, f'메일 발송에 실패했습니다. 관리자에게 문의해주세요. 임시 비밀번호: {temp_pw}')

    return render(request, 'registration/password_reset.html')


@login_required
def dashboard(request):
    leave_balance = LeaveBalance.objects.filter(user=request.user).first()
    if not leave_balance:
        leave_balance = LeaveBalance(user=request.user, total_leave=15, used_leave=0)

    leave_summary = _leave_summary_for_user(request.user)
    today = timezone.localdate()
    week_end = today + timedelta(days=6)
    weekly_highlights = {'leave': [], 'trip': [], 'meeting': [], 'personal': []}

    my_leaves = LeaveRequest.objects.filter(user=request.user).order_by('-start_date')
    my_trips = TripRequest.objects.filter(
        Q(user=request.user) | Q(participants=request.user)
    ).distinct().order_by('-start_date')
    pending_trip_reports = TripRequest.objects.filter(
        user=request.user,
        status='approved'
    ).filter(Q(report_content__isnull=True) | Q(report_content='')).count()

    calendar_events = []

    leave_qs = LeaveRequest.objects.filter(status='approved').select_related('user')
    for leave in leave_qs:
        mine = leave.user_id == request.user.id
        color = '#4c6ef5' if mine else '#adb5bd'
        if mine and leave.start_date <= week_end and leave.end_date >= today:
            weekly_highlights['leave'].append({
                'title': leave.leave_type,
                'detail': f"{leave.start_date.strftime('%m-%d')} ~ {leave.end_date.strftime('%m-%d')}",
                'order': leave.start_date,
            })
        calendar_events.append({
            'title': leave.reason if leave.reason else leave.leave_type,
            'start': leave.start_date.isoformat(),
            'end': (leave.end_date + timedelta(days=1)).isoformat(),
            'allDay': True,
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'type': 'leave',
                'id': leave.id,
                'user': leave.user.username,
                'range': f"{leave.start_date} ~ {leave.end_date}",
                'reason': leave.reason,
                'mine': mine,
                'title': leave.leave_type,
                'canManage': mine,
                'deleteUrl': reverse('leave_delete', args=[leave.id]) if mine else '',
            },
        })

    trip_qs = TripRequest.objects.filter(status='approved').select_related('user')
    trip_qs = trip_qs.prefetch_related('participants')
    for trip in trip_qs:
        owner = trip.user_id == request.user.id
        participant_ids = [p.id for p in trip.participants.all()]
        is_participant = request.user.id in participant_ids
        mine_for_color = owner or is_participant
        color = '#0dcaf0' if mine_for_color else '#adb5bd'
        is_all_day = getattr(trip, 'all_day', False)
        start_dt = timezone.localtime(trip.start_date)
        end_dt = timezone.localtime(trip.end_date)
        participant_names = [p.username for p in trip.participants.all()]
        if mine_for_color and start_dt.date() <= week_end and end_dt.date() >= today:
            weekly_highlights['trip'].append({
                'title': trip.location or trip.purpose,
                'detail': f"{start_dt.strftime('%m-%d')}" + (" 종일" if is_all_day else f" {start_dt.strftime('%H:%M')}") + (f" ~ {end_dt.strftime('%m-%d %H:%M')}" if not is_all_day else ''),
                'order': start_dt,
            })
        calendar_events.append({
            'title': trip.location,
            'start': start_dt.date().isoformat() if is_all_day else start_dt.isoformat(),
            'end': (end_dt.date() + timedelta(days=1)).isoformat() if is_all_day else end_dt.isoformat(),
            'allDay': is_all_day,
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'type': 'trip',
                'id': trip.id,
                'user': trip.user.username,
                'range': f"{start_dt.strftime('%Y-%m-%d %p %I:%M')} ~ {end_dt.strftime('%Y-%m-%d %p %I:%M')}",
                'location': trip.location,
                'purpose': trip.purpose,
                'mine': mine_for_color,
                'title': trip.purpose,
                'canManage': owner,
                'editUrl': reverse('trip_update', args=[trip.id]) if owner else '',
                'deleteUrl': reverse('trip_delete', args=[trip.id]) if owner else '',
                'participants': participant_names,
            },
        })

    meeting_qs = Meeting.objects.select_related('user').prefetch_related('participants')
    for meeting in meeting_qs:
        owner = meeting.user_id == request.user.id
        participant_ids = [p.id for p in meeting.participants.all()]
        is_participant = request.user.id in participant_ids
        mine_for_color = owner or is_participant
        color = '#20c997' if mine_for_color else '#adb5bd'
        is_all_day = getattr(meeting, 'all_day', False)
        start_dt = timezone.localtime(meeting.start_date)
        end_dt = timezone.localtime(meeting.end_date)
        participant_names = [p.username for p in meeting.participants.all()]
        if mine_for_color and start_dt.date() <= week_end and end_dt.date() >= today:
            weekly_highlights['meeting'].append({
                'title': meeting.subject,
                'detail': f"{start_dt.strftime('%m-%d')}" + (" 종일" if is_all_day else f" {start_dt.strftime('%H:%M')}") + (f" ~ {end_dt.strftime('%m-%d %H:%M')}" if not is_all_day else ''),
                'order': start_dt,
            })
        calendar_events.append({
            'title': meeting.subject,
            'start': start_dt.date().isoformat() if is_all_day else start_dt.isoformat(),
            'end': (end_dt.date() + timedelta(days=1)).isoformat() if is_all_day else end_dt.isoformat(),
            'allDay': is_all_day,
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'type': 'meeting',
                'id': meeting.id,
                'user': meeting.user.username,
                'range': f"{start_dt.strftime('%Y-%m-%d %p %I:%M')} ~ {end_dt.strftime('%Y-%m-%d %p %I:%M')}",
                'purpose': meeting.subject,
                'mine': mine_for_color,
                'title': meeting.subject,
                'participants': participant_names,
            },
        })

    personal_qs = PersonalEvent.objects.filter(user=request.user)
    for p in personal_qs:
        is_all_day = getattr(p, 'all_day', False)
        start_dt = timezone.localtime(p.start_date)
        end_dt = timezone.localtime(p.end_date)
        color = '#be4bdb'
        if start_dt.date() <= week_end and end_dt.date() >= today:
            weekly_highlights['personal'].append({
                'title': p.title,
                'detail': f"{start_dt.strftime('%m-%d')}" + (" 종일" if is_all_day else f" {start_dt.strftime('%H:%M')}") + (f" ~ {end_dt.strftime('%m-%d %H:%M')}" if not is_all_day else ''),
                'order': start_dt,
            })
        calendar_events.append({
            'title': p.title,
            'start': start_dt.date().isoformat() if is_all_day else start_dt.isoformat(),
            'end': (end_dt.date() + timedelta(days=1)).isoformat() if is_all_day else end_dt.isoformat(),
            'allDay': is_all_day,
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'extendedProps': {
                'type': 'personal',
                'id': p.id,
                'user': p.user.username,
                'range': f"{start_dt.strftime('%Y-%m-%d %p %I:%M')} ~ {end_dt.strftime('%Y-%m-%d %p %I:%M')}",
                'purpose': p.description or p.title,
                'mine': True,
                'title': p.title,
                'location': p.location,
                'canManage': True,
                'editUrl': reverse('personal_update', args=[p.id]),
                'deleteUrl': reverse('personal_delete', args=[p.id]),
            },
        })

    for key in weekly_highlights:
        weekly_highlights[key] = sorted(weekly_highlights[key], key=lambda x: x.get('order'))

    type_labels = {'leave': '휴가', 'trip': '외부일정', 'meeting': '미팅', 'personal': '개인'}
    type_colors = {'leave': '#4c6ef5', 'trip': '#0dcaf0', 'meeting': '#20c997', 'personal': '#be4bdb'}
    grouped_highlights = {}
    for key, items in weekly_highlights.items():
        for item in items:
            order_val = item.get('order')
            day = order_val.date() if hasattr(order_val, 'date') else order_val
            if not day:
                continue
            grouped_highlights.setdefault(day, []).append({
                'type': type_labels.get(key, ''),
                'title': item.get('title'),
                'detail': item.get('detail'),
                'color': type_colors.get(key, '#6c757d'),
            })

    weekly_highlights_by_date = []
    for day in sorted(grouped_highlights.keys()):
        weekly_highlights_by_date.append({
            'label': day.strftime('%m/%d'),
            'items': grouped_highlights[day],
        })

    return render(request, 'attendance/dashboard.html', {
        'leave_balance': leave_balance,
        'leave_summary': leave_summary,
        'my_leaves': my_leaves,
        'my_trips': my_trips,
        'pending_trip_reports': pending_trip_reports,
        'calendar_events_json': json.dumps(calendar_events, ensure_ascii=False),
        'weekly_highlights': weekly_highlights,
        'week_range_label': f"{today.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}",
        'weekly_highlights_by_date_json': json.dumps(weekly_highlights_by_date, ensure_ascii=False),
    })


@login_required
def leave_create(request):
    if request.method == 'POST':
        form = LeaveForm(request.POST)
        if form.is_valid():
            leave_req = form.save(commit=False)
            leave_req.user = request.user
            leave_req.save()
            approvers = [form.cleaned_data.get('approver1'), form.cleaned_data.get('approver2'), form.cleaned_data.get('approver3')]
            order = 1
            for approver in [a for a in approvers if a]:
                LeaveApprovalStep.objects.create(leave=leave_req, approver=approver, order=order)
                order += 1
            messages.success(request, '휴가 신청이 완료되었습니다.')
            return redirect('dashboard')
    else:
        form = LeaveForm()
    return render(request, 'attendance/leave_form.html', {'form': form})


@login_required
def trip_create(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip_req = form.save(commit=False)
            trip_req.user = request.user
            trip_req.status = 'approved'  # 출장은 통보 형식으로 자동 승인
            _normalize_all_day_event(trip_req)
            trip_req.save()
            form.save_m2m()
            messages.success(request, '출장 신청이 완료되었습니다.')
            return redirect('dashboard')
    else:
        form = TripForm()
    return render(request, 'attendance/trip_form.html', {'form': form})


@login_required
def meeting_create(request):
    if request.method == 'POST':
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.user = request.user
            _normalize_all_day_event(meeting)
            meeting.save()
            form.save_m2m()
            messages.success(request, '미팅이 등록되었습니다.')
            return redirect('dashboard')
    else:
        form = MeetingForm()
    return render(request, 'attendance/meeting_form.html', {'form': form})


@login_required
def personal_create(request):
    if request.method == 'POST':
        form = PersonalEventForm(request.POST)
        if form.is_valid():
            personal = form.save(commit=False)
            personal.user = request.user
            _normalize_all_day_event(personal)
            personal.save()
            messages.success(request, '개인일정이 등록되었습니다.')
            return redirect('dashboard')
    else:
        form = PersonalEventForm()
    return render(request, 'attendance/personal_form.html', {'form': form, 'is_edit': False})


@login_required
def personal_update(request, pk):
    personal = get_object_or_404(PersonalEvent, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PersonalEventForm(request.POST, instance=personal)
        if form.is_valid():
            personal = form.save(commit=False)
            personal.user = request.user
            _normalize_all_day_event(personal)
            personal.save()
            messages.success(request, '개인 일정이 수정되었습니다.')
            return redirect('dashboard')
    else:
        form = PersonalEventForm(instance=personal)
    return render(request, 'attendance/personal_form.html', {'form': form, 'is_edit': True})


@login_required
def personal_delete(request, pk):
    personal = get_object_or_404(PersonalEvent, pk=pk, user=request.user)
    if request.method == 'POST':
        personal.delete()
        messages.success(request, '개인 일정이 삭제되었습니다.')
    else:
        messages.error(request, '잘못된 요청입니다.')
    return redirect('dashboard')


@login_required
def trip_report(request, trip_id):
    trip = get_object_or_404(TripRequest, id=trip_id, user=request.user)
    if request.method == 'POST':
        form = TripReportForm(request.POST, instance=trip)
        if form.is_valid():
            form.save()
            messages.success(request, '출장 보고서가 제출되었습니다.')
            return redirect('dashboard')
    else:
        form = TripReportForm(instance=trip)
    return render(request, 'attendance/trip_report.html', {'trip': trip, 'form': form})


@login_required
def trip_update(request, trip_id):
    trip = get_object_or_404(TripRequest, id=trip_id, user=request.user)
    if request.method == 'POST':
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            trip_req = form.save(commit=False)
            _normalize_all_day_event(trip_req)
            trip_req.save()
            form.save_m2m()
            messages.success(request, '출장 신청을 수정했습니다.')
            return redirect('dashboard')
    else:
        form = TripForm(instance=trip)
    return render(request, 'attendance/trip_form.html', {'form': form, 'is_edit': True, 'trip_obj': trip})


@login_required
def trip_delete(request, trip_id):
    trip = get_object_or_404(TripRequest, id=trip_id, user=request.user)
    if request.method != 'POST':
        return HttpResponseForbidden('잘못된 요청입니다.')
    trip.delete()
    messages.success(request, '출장 신청을 삭제했습니다.')
    return redirect('dashboard')


def trip_report_quick_update(request):
    if request.method != 'POST':
        return HttpResponseForbidden('잘못된 요청입니다.')
    trip_id = request.POST.get('trip_id')
    content = request.POST.get('report_content', '').strip()
    trip = get_object_or_404(TripRequest, id=trip_id, user=request.user)
    trip.report_content = content
    trip.save()
    messages.success(request, '출장 보고서를 저장했습니다.')
    return redirect('dashboard')


@login_required
def leave_approval_list(request):
    if not _user_in_groups(request.user, ['휴가 결재권자', '경영관리부']):
        return HttpResponseForbidden('휴가 결재 권한이 필요합니다.')

    pending_steps = LeaveApprovalStep.objects.filter(
        approver=request.user,
        status='pending',
        leave__status='pending',
    ).select_related('leave', 'leave__user').prefetch_related('leave__approval_steps__approver').order_by('order', 'leave__start_date')

    actionable = []
    for step in pending_steps:
        prior_exists = step.leave.approval_steps.filter(order__lt=step.order).exclude(status='approved').exists()
        if not prior_exists:
            actionable.append(step)

    if request.method == 'POST':
        action = request.POST.get('action')
        step_id = request.POST.get('step_id')
        step = get_object_or_404(LeaveApprovalStep, pk=step_id, approver=request.user)
        leave = step.leave
        if leave.status != 'pending' or step.status != 'pending':
            messages.warning(request, '이미 처리된 신청입니다.')
            return redirect('leave_approval')

        if leave.approval_steps.filter(order__lt=step.order).exclude(status='approved').exists():
            messages.warning(request, '이전 결재가 완료되어야 합니다.')
            return redirect('leave_approval')

        if action == 'approve':
            step.status = 'approved'
            step.decided_at = timezone.now()
        elif action == 'reject':
            step.status = 'rejected'
            step.decided_at = timezone.now()
            leave.status = 'rejected'
        step.save()

        if step.status == 'approved':
            remaining_pending = leave.approval_steps.filter(status='pending').exists()
            if not remaining_pending:
                leave.status = 'approved'
        leave.save()

        if step.status == 'approved':
            messages.success(request, f'{leave.user.username}님의 휴가를 승인했습니다.')
        else:
            messages.info(request, f'{leave.user.username}님의 휴가를 반려했습니다.')
        return redirect('leave_approval')

    return render(request, 'attendance/leave_approval.html', {'actionable_steps': actionable})


@login_required
def leave_delete(request, leave_id):
    leave_req = get_object_or_404(LeaveRequest, id=leave_id, user=request.user)
    if request.method != 'POST':
        return HttpResponseForbidden('잘못된 요청입니다.')
    leave_req.delete()
    messages.success(request, '휴가 신청을 삭제했습니다.')
    return redirect('dashboard')


@login_required
def trip_approval_list(request):
    if not _user_in_groups(request.user, ['출장 결재권자']):
        return HttpResponseForbidden('출장 결재 권한이 필요합니다.')

    pending = TripRequest.objects.filter(status='pending').select_related('user').order_by('start_date')

    if request.method == 'POST':
        action = request.POST.get('action')
        trip_id = request.POST.get('trip_id')
        trip = get_object_or_404(TripRequest, pk=trip_id)
        if trip.status != 'pending':
            messages.warning(request, '이미 처리된 신청입니다.')
            return redirect('trip_approval')
        if action == 'approve':
            trip.status = 'approved'
            trip.save()
            messages.success(request, f'{trip.user.username}님의 출장을 승인했습니다.')
        elif action == 'reject':
            trip.status = 'rejected'
            trip.save()
            messages.info(request, f'{trip.user.username}님의 출장을 반려했습니다.')
        return redirect('trip_approval')

    return render(request, 'attendance/trip_approval.html', {'pending_trips': pending})


@login_required
def management_overview(request):
    if not _user_in_groups(request.user, ['경영관리부']):
        return HttpResponseForbidden('경영관리부 권한이 필요합니다.')

    User = get_user_model()
    users = User.objects.all().order_by('username')

    window_start = timezone.now() - timedelta(days=30)
    trip_counts = TripRequest.objects.filter(status='approved', start_date__gte=window_start).values('user_id').annotate(cnt=models.Count('id'))

    external_map = {row['user_id']: row['cnt'] for row in trip_counts}

    user_rows = []
    total_leave = 0
    total_used = 0
    total_remaining = 0
    usage_rates = []

    for u in users:
        summary = _leave_summary_for_user(u)
        total_leave += summary['earned']
        total_used += summary['used']
        total_remaining += summary['remaining']
        if summary['earned'] > 0:
            usage_rates.append(summary['usage_rate'])
        user_rows.append({
            'username': u.username,
            'department': getattr(u, 'department', ''),
            'position': getattr(u, 'position', ''),
            'earned': summary['earned'],
            'used': summary['used'],
            'remaining': summary['remaining'],
            'missing_join_date': summary['missing_join_date'],
            'join_date': summary['join_date'],
            'usage_rate': summary['usage_rate'],
            'reset_date': summary['reset_date'],
            'external_30d': external_map.get(u.id, 0),
        })

    leaves = LeaveRequest.objects.filter(status='approved').select_related('user').order_by('-start_date')[:50]
    trips = TripRequest.objects.filter(status='approved').select_related('user').order_by('-start_date')[:50]

    total_users = users.count()
    avg_usage = round(sum(usage_rates) / len(usage_rates), 1) if usage_rates else 0
    avg_earned = round(total_leave / total_users, 1) if total_users else 0
    avg_remaining = round(total_remaining / total_users, 1) if total_users else 0

    return render(request, 'attendance/management_overview.html', {
        'user_rows': user_rows,
        'recent_leaves': leaves,
        'recent_trips': trips,
        'total_users': total_users,
        'avg_usage': avg_usage,
        'avg_earned': avg_earned,
        'avg_remaining': avg_remaining,
    })


@login_required
def admin_role_management(request):
    if not _user_in_groups(request.user, [ADMIN_GROUP]):
        return HttpResponseForbidden('관리자 권한이 필요합니다.')

    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)

    User = get_user_model()

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        selected = request.POST.getlist('groups')
        target = get_object_or_404(User, pk=user_id)
        target.groups.remove(*Group.objects.filter(name__in=ROLE_GROUPS))
        if selected:
            add_groups = Group.objects.filter(name__in=selected)
            target.groups.add(*add_groups)
        messages.success(request, f"{target.username}님의 권한을 업데이트했습니다.")
        return redirect('admin_roles')

    group_map = {g.name: g for g in Group.objects.filter(name__in=ROLE_GROUPS)}
    user_rows = []
    for u in User.objects.all().order_by('username'):
        user_rows.append({
            'id': u.id,
            'username': u.username,
            'department': getattr(u, 'department', ''),
            'position': getattr(u, 'position', ''),
            'groups': set(u.groups.values_list('name', flat=True)),
        })

    return render(request, 'attendance/admin_roles.html', {
        'role_groups': ROLE_GROUPS,
        'users': user_rows,
    })


@login_required
def admin_user_management(request):
    if not _user_in_groups(request.user, [ADMIN_GROUP]):
        return HttpResponseForbidden('관리자 권한이 필요합니다.')

    User = get_user_model()

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        target = get_object_or_404(User, pk=user_id)

        if action == 'update':
            target.email = request.POST.get('email', '').strip()
            target.department = request.POST.get('department', '').strip()
            target.position = request.POST.get('position', '').strip()
            target.is_active = bool(request.POST.get('is_active'))
            join_date_raw = request.POST.get('join_date', '').strip()
            if join_date_raw:
                try:
                    target.join_date = timezone.datetime.strptime(join_date_raw, '%Y-%m-%d').date()
                except ValueError:
                    messages.warning(request, '입사일 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요.')
            target.save(update_fields=['email', 'department', 'position', 'is_active', 'join_date'])
            messages.success(request, f"{target.username} 정보를 업데이트했습니다.")

        elif action == 'reset_password':
            new_pw = User.objects.make_random_password()
            target.set_password(new_pw)
            target.save(update_fields=['password'])
            messages.success(request, f"{target.username}의 비밀번호를 재설정했습니다: {new_pw}")

        elif action == 'delete':
            if target == request.user:
                messages.warning(request, '본인 계정은 삭제할 수 없습니다.')
            else:
                username = target.username
                target.delete()
                messages.success(request, f"{username} 계정을 삭제했습니다.")

        return redirect('admin_users')

    users = User.objects.all().order_by('username')
    return render(request, 'attendance/admin_users.html', {'users': users})


@login_required
def trip_report_inbox(request):
    if not (_is_trip_recipient(request.user) or _user_in_groups(request.user, [ADMIN_GROUP])):
        return HttpResponseForbidden('보고서 열람 권한이 필요합니다.')

    q = request.GET.get('q', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    reports = TripRequest.objects.filter(report_content__isnull=False).exclude(report_content='').select_related('user').prefetch_related('participants')

    if q:
        reports = reports.filter(
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )

    if start_date:
        try:
            reports = reports.filter(start_date__date__gte=timezone.datetime.strptime(start_date, '%Y-%m-%d').date())
        except ValueError:
            messages.warning(request, '시작일 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요.')

    if end_date:
        try:
            reports = reports.filter(end_date__date__lte=timezone.datetime.strptime(end_date, '%Y-%m-%d').date())
        except ValueError:
            messages.warning(request, '종료일 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요.')

    reports = reports.order_by('-start_date')

    return render(request, 'attendance/trip_report_inbox.html', {
        'reports': reports,
        'filter_q': q,
        'filter_start_date': start_date,
        'filter_end_date': end_date,
    })


@login_required
def trip_report_recipients(request):
    if not _user_in_groups(request.user, [ADMIN_GROUP]):
        return HttpResponseForbidden('관리자 권한이 필요합니다.')

    User = get_user_model()
    users = User.objects.all().order_by('username')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('recipients')
        TripReportRecipient.objects.all().delete()
        if selected_ids:
            recipients = User.objects.filter(id__in=selected_ids)
            for u in recipients:
                TripReportRecipient.objects.create(user=u)
        messages.success(request, '출장 보고 수신자를 업데이트했습니다.')
        return redirect('trip_recipients')

    current_ids = set(TripReportRecipient.objects.values_list('user_id', flat=True))
    return render(request, 'attendance/trip_recipients.html', {
        'users': users,
        'current_ids': current_ids,
    })
