"""URL routing for runs app."""

from django.urls import path

from runs.views import (
    RunCancelView,
    RunCollectionView,
    RunDetailView,
    RunRetryFailedView,
)

app_name = "runs"

urlpatterns = [
    path("", RunCollectionView.as_view(), name="runs-collection"),
    path("<int:pk>/", RunDetailView.as_view(), name="runs-detail"),
    path("<int:pk>/cancel/", RunCancelView.as_view(), name="runs-cancel"),
    path("<int:pk>/retry-failed/", RunRetryFailedView.as_view(), name="runs-retry-failed"),
]