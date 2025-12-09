from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView

from attendance import views as attendance_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(template_name='attendance/password_change.html', success_url='/accounts/password_change/done/'), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='attendance/password_change_done.html'), name='password_change_done'),
    path('attendance/', include('attendance.urls')),
    path('', RedirectView.as_view(url='/attendance/', permanent=False)),
]