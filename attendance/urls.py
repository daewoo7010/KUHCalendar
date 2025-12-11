from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('signup/', views.signup, name='signup'),
    path('leave/new/', views.leave_create, name='leave_create'),
    path('leave/<int:leave_id>/delete/', views.leave_delete, name='leave_delete'),
    path('trip/new/', views.trip_create, name='trip_create'),
    path('meeting/new/', views.meeting_create, name='meeting_create'),
    path('personal/new/', views.personal_create, name='personal_create'),
    path('trip/<int:trip_id>/edit/', views.trip_update, name='trip_update'),
    path('trip/<int:trip_id>/delete/', views.trip_delete, name='trip_delete'),
    path('trip/report/<int:trip_id>/', views.trip_report, name='trip_report'),
    path('trip/report/quick/', views.trip_report_quick_update, name='trip_report_quick'),
    path('approvals/leave/', views.leave_approval_list, name='leave_approval'),
    path('approvals/trip/', views.trip_approval_list, name='trip_approval'),
    path('management/overview/', views.management_overview, name='management_overview'),
    path('admin/roles/', views.admin_role_management, name='admin_roles'),
    path('admin/users/', views.admin_user_management, name='admin_users'),
    path('reports/trip/', views.trip_report_inbox, name='trip_report_inbox'),
    path('admin/trip-recipients/', views.trip_report_recipients, name='trip_recipients'),
]
