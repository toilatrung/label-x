"""URL đọc Evaluation: /api/candidate-evaluations/."""

from django.urls import path

from orchestration.evaluation_views import EvaluationDetailView

app_name = "evaluations"

urlpatterns = [
    path("<int:pk>/", EvaluationDetailView.as_view(), name="evaluation-detail"),
]
