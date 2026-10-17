"""URL của tài nguyên candidate cho Evaluation: /api/candidates/."""

from django.urls import path

from orchestration.evaluation_views import CandidateEvaluationCreateView

app_name = "candidates"

urlpatterns = [
    path(
        "<int:pk>/evaluations/", CandidateEvaluationCreateView.as_view(), name="candidate-evaluate"
    ),
]
