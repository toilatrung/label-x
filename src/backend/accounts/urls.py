from django.urls import path

from accounts.views import (
    CsrfView,
    LoginView,
    LogoutView,
    SessionView,
    WorkflowPermissionsView,
    WorkflowRuleUpdateView,
)

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("session/", SessionView.as_view(), name="auth-session"),
    path(
        "workflow-permissions/", WorkflowPermissionsView.as_view(), name="auth-workflow-permissions"
    ),
    path(
        "workflow-permissions/rules/<str:rule>/",
        WorkflowRuleUpdateView.as_view(),
        name="auth-workflow-rule-update",
    ),
]
