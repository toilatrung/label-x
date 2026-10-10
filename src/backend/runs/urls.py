"""URL routing for runs app."""

from django.urls import path

from runs.views import (
    RunCancelView,
    RunCollectionView,
    RunDetailView,
    RunFrameImageView,
    RunFrameListView,
    RunLedgerView,
    RunRetryFailedView,
    RunShardView,
)

app_name = "runs"

urlpatterns = [
    path("", RunCollectionView.as_view(), name="runs-collection"),
    path("<int:pk>/", RunDetailView.as_view(), name="runs-detail"),
    path("<int:pk>/cancel/", RunCancelView.as_view(), name="runs-cancel"),
    path("<int:pk>/retry-failed/", RunRetryFailedView.as_view(), name="runs-retry-failed"),
    path("<int:pk>/ledger/", RunLedgerView.as_view(), name="runs-ledger"),
    path("<int:pk>/shards/", RunShardView.as_view(), name="runs-shards"),
    path("<int:pk>/frames/", RunFrameListView.as_view(), name="runs-frames"),
    path(
        "<int:pk>/frames/<int:frame_id>/image/",
        RunFrameImageView.as_view(),
        name="runs-frame-image",
    ),
]
