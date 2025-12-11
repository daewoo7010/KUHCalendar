from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import CustomUser, LeaveRequest, TripRequest, Meeting, PersonalEvent


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    department = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    position = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    join_date = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}), label='입사일')

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'department', 'position', 'join_date', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Normalize password widgets to Bootstrap form-control
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})


class LeaveForm(forms.ModelForm):
    approver1 = forms.ModelChoiceField(queryset=None, required=False, label='결재자 1', widget=forms.Select(attrs={'class': 'form-select'}))
    approver2 = forms.ModelChoiceField(queryset=None, required=False, label='결재자 2', widget=forms.Select(attrs={'class': 'form-select'}))
    approver3 = forms.ModelChoiceField(queryset=None, required=False, label='결재자 3', widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        approvers = User.objects.filter(groups__name__in=['휴가 결재권자', '경영관리부']).distinct().order_by('username')
        for key in ['approver1', 'approver2', 'approver3']:
            self.fields[key].queryset = approvers

    def clean(self):
        cleaned = super().clean()
        approvers = [cleaned.get('approver1'), cleaned.get('approver2'), cleaned.get('approver3')]
        approvers = [a for a in approvers if a]
        if not approvers:
            raise forms.ValidationError('최소 1명의 결재자를 선택해주세요.')
        if len(set(approvers)) != len(approvers):
            raise forms.ValidationError('동일한 결재자를 중복 선택할 수 없습니다.')
        return cleaned


class TripForm(forms.ModelForm):
    class Meta:
        model = TripRequest
        fields = ['location', 'purpose', 'start_date', 'end_date', 'all_day', 'participants']
        widgets = {
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'purpose': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'all_day': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'participants': forms.SelectMultiple(attrs={'class': 'form-select d-none', 'size': 8, 'style': 'display:none;'}),
        }
        labels = {
            'start_date': '시작 일시',
            'end_date': '종료 일시',
            'all_day': '종일',
            'participants': '동석자 (복수 선택 가능)',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        all_day = cleaned.get('all_day')

        if all_day:
            # 종일인 경우 시각 단위 검증은 생략 (후처리에서 정규화)
            return cleaned

        def _invalid_step(dt):
            return dt and (dt.minute % 10 != 0 or dt.second != 0 or dt.microsecond != 0)

        if _invalid_step(start):
            self.add_error('start_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')
        if _invalid_step(end):
            self.add_error('end_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')

        if start and end and end < start:
            self.add_error('end_date', '종료 일시는 시작 일시보다 빠를 수 없습니다.')

        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields['participants'].queryset = User.objects.order_by('username')


class TripReportForm(forms.ModelForm):
    class Meta:
        model = TripRequest
        fields = ['report_content']
        widgets = {
            'report_content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }
        labels = {
            'report_content': '출장 결과 보고',
        }


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['subject', 'start_date', 'end_date', 'all_day', 'participants']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'all_day': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'participants': forms.SelectMultiple(attrs={'class': 'form-select d-none', 'size': 8, 'style': 'display:none;'}),
        }
        labels = {
            'subject': '미팅 주제',
            'start_date': '시작 일시',
            'end_date': '종료 일시',
            'all_day': '종일',
            'participants': '동석자 (복수 선택 가능)',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        all_day = cleaned.get('all_day')

        if all_day:
            return cleaned

        def _invalid_step(dt):
            return dt and (dt.minute % 10 != 0 or dt.second != 0 or dt.microsecond != 0)

        if _invalid_step(start):
            self.add_error('start_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')
        if _invalid_step(end):
            self.add_error('end_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')

        if start and end and end < start:
            self.add_error('end_date', '종료 일시는 시작 일시보다 빠를 수 없습니다.')

        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields['participants'].queryset = User.objects.order_by('username')


class PersonalEventForm(forms.ModelForm):
    class Meta:
        model = PersonalEvent
        fields = ['title', 'location', 'description', 'start_date', 'end_date', 'all_day']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '600'}),
            'all_day': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': '제목',
            'location': '장소',
            'description': '메모',
            'start_date': '시작 일시',
            'end_date': '종료 일시',
            'all_day': '종일',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        all_day = cleaned.get('all_day')

        if all_day:
            return cleaned

        def _invalid_step(dt):
            return dt and (dt.minute % 10 != 0 or dt.second != 0 or dt.microsecond != 0)

        if _invalid_step(start):
            self.add_error('start_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')
        if _invalid_step(end):
            self.add_error('end_date', '10분 단위(분: 00, 10, 20, 30, 40, 50)로 입력해주세요.')

        if start and end and end < start:
            self.add_error('end_date', '종료 일시는 시작 일시보다 빠를 수 없습니다.')

        return cleaned
