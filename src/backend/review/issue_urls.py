from django.urls import path

from review.issue_views import IssueDecisionView, IssueDetailView, ManualIssueView

urlpatterns = [
    path("", ManualIssueView.as_view(), name="issues-create"),
    path("<int:pk>/", IssueDetailView.as_view(), name="issues-detail"),
    path("<int:pk>/decisions/", IssueDecisionView.as_view(), name="issues-decide"),
]
