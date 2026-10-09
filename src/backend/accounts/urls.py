from django.urls import path

from accounts.views import CsrfView, LoginView, LogoutView, SessionView, WorkflowPermissionsView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("session/", SessionView.as_view(), name="auth-session"),
    path(
        "workflow-permissions/", WorkflowPermissionsView.as_view(), name="auth-workflow-permissions"
    ),
]
