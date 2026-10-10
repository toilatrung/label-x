"""URL routing for runs app."""

from django.urls import path

from runs.views import (
    RunCancelView,
    RunCandidateListView,
    RunCollectionView,
    RunDetailView,
    RunFrameImageView,
    RunFrameListView,
    RunLedgerView,
    RunRankingView,
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
    path("<int:pk>/candidates/", RunCandidateListView.as_view(), name="runs-candidates"),
    path("<int:pk>/ranking/", RunRankingView.as_view(), name="runs-ranking"),
    path("<int:pk>/frames/", RunFrameListView.as_view(), name="runs-frames"),
    path(
        "<int:pk>/frames/<int:frame_id>/image/",
        RunFrameImageView.as_view(),
        name="runs-frame-image",
    ),
]
