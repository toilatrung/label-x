from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from calibration.views import (
    AuditSampleListCreateView,
    BenchmarkImportCvatView,
    BenchmarkListCreateView,
    EvaluationPerformanceView,
)
from orchestration.metrics_view import MetricsView
from review.adjudication_views import (
    DecisionCaseDetailView,
    DecisionCaseListView,
    EscalationsListView,
)
from review.gap_views import GuidelineGapCollectionView
from runs.views import ConfigVersionListView, ConfigVersionPublishView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("internal/metrics/", MetricsView.as_view(), name="internal-metrics"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/auth/", include("accounts.urls")),
    path("api/guidelines/", include("guideline.urls")),
    path("api/snapshots/", include("snapshots.urls")),
    path("api/datasets/", include("snapshots.dataset_urls")),
    path("api/runs/", include("runs.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/releases/", include("releases.urls")),
    path("api/candidates/", include("orchestration.candidate_urls")),
    path("api/candidate-evaluations/", include("orchestration.evaluation_urls")),
    path("api/queues/", include("review.queue_urls")),
    path("api/leases/", include("review.lease_urls")),
    path("api/frames/", include("review.frame_urls")),
    path("api/issues/", include("review.issue_urls")),
    path("api/rework/", include("review.rework_urls")),
    path("api/effort-events/", include("effort.urls")),
    path("api/review-policy/", include("review.policy_urls")),
    path("api/escalations/", EscalationsListView.as_view(), name="escalations-list"),
    path("api/guideline-gaps/", GuidelineGapCollectionView.as_view(), name="guideline-gaps"),
    path("api/decision-cases/", DecisionCaseListView.as_view(), name="decision-cases-list"),
    path(
        "api/decision-cases/<int:pk>/",
        DecisionCaseDetailView.as_view(),
        name="decision-cases-detail",
    ),
    path("api/config-versions/", ConfigVersionListView.as_view(), name="config-versions-list"),
    path(
        "api/config-versions/<int:pk>/publish/",
        ConfigVersionPublishView.as_view(),
        name="config-versions-publish",
    ),
    path(
        "api/audit-samples/", AuditSampleListCreateView.as_view(), name="audit-samples-list-create"
    ),
    path(
        "api/benchmarks/import-cvat/",
        BenchmarkImportCvatView.as_view(),
        name="benchmarks-import-cvat",
    ),
    path("api/benchmarks/", BenchmarkListCreateView.as_view(), name="benchmarks-list-create"),
    path(
        "api/evaluation/performance/",
        EvaluationPerformanceView.as_view(),
        name="evaluation-performance",
    ),
    path("api/calibration/", include("calibration.urls")),
]
