"""URL routing for calibration sub-paths: /api/calibration/."""

from django.urls import path

from calibration.views import (
    CalibrationAssignmentsCreateView,
    CalibrationModelsListView,
    CalibrationReviewersListView,
)

urlpatterns = [
    path("reviewers/", CalibrationReviewersListView.as_view(), name="calibration-reviewers-list"),
    path("models/", CalibrationModelsListView.as_view(), name="calibration-models-list"),
    path(
        "assignments/",
        CalibrationAssignmentsCreateView.as_view(),
        name="calibration-assignments-create",
    ),
]
