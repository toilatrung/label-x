from django.urls import path

from review.adjudication_views import IssueAdjudicationView
from review.issue_views import IssueDecisionView, IssueDetailView, ManualIssueView

urlpatterns = [
    path("", ManualIssueView.as_view(), name="issues-create"),
    path("<int:pk>/", IssueDetailView.as_view(), name="issues-detail"),
    path("<int:pk>/decisions/", IssueDecisionView.as_view(), name="issues-decide"),
    path("<int:pk>/adjudications/", IssueAdjudicationView.as_view(), name="issues-adjudicate"),
]
