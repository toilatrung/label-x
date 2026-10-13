"""URL routing for runs app."""

from django.urls import path

from reports.views import RunReportExportView, RunReportView
from runs.summary_views import (
    RunCandidateCategoriesView,
    RunEnginesStatsView,
    RunMetricsView,
    RunReviewVolumeView,
    RunTasksQualityView,
)
from runs.views import (
    RunCancelView,
    RunCandidateListView,
    RunCollectionView,
    RunDetailView,
    RunLedgerView,
    RunLineageView,
    RunRankingView,
    RunRetryFailedView,
    RunShardView,
)

app_name = "runs"

urlpatterns = [
    path("<int:pk>/metrics/", RunMetricsView.as_view(), name="runs-metrics"),
    path("<int:pk>/engines/", RunEnginesStatsView.as_view(), name="runs-engines-stats"),
    path("<int:pk>/review-volume/", RunReviewVolumeView.as_view(), name="runs-review-volume"),
    path("<int:pk>/tasks-quality/", RunTasksQualityView.as_view(), name="runs-tasks-quality"),
    path(
        "<int:pk>/candidate-categories/",
        RunCandidateCategoriesView.as_view(),
        name="runs-candidate-categories",
    ),
    path("", RunCollectionView.as_view(), name="runs-collection"),
    path("<int:pk>/", RunDetailView.as_view(), name="runs-detail"),
    path("<int:pk>/cancel/", RunCancelView.as_view(), name="runs-cancel"),
    path("<int:pk>/retry-failed/", RunRetryFailedView.as_view(), name="runs-retry-failed"),
    path("<int:pk>/lineage/", RunLineageView.as_view(), name="runs-lineage"),
    path("<int:pk>/ledger/", RunLedgerView.as_view(), name="runs-ledger"),
    path("<int:pk>/shards/", RunShardView.as_view(), name="runs-shards"),
    path("<int:pk>/candidates/", RunCandidateListView.as_view(), name="runs-candidates"),
    path("<int:pk>/ranking/", RunRankingView.as_view(), name="runs-ranking"),
    path("<int:pk>/report/", RunReportView.as_view(), name="runs-report"),
    path("<int:pk>/report/export/", RunReportExportView.as_view(), name="runs-report-export"),
]
