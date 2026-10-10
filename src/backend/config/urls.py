from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from runs.views import ConfigVersionListView, ConfigVersionPublishView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/auth/", include("accounts.urls")),
    path("api/guidelines/", include("guideline.urls")),
    path("api/snapshots/", include("snapshots.urls")),
    path("api/datasets/", include("snapshots.dataset_urls")),
    path("api/runs/", include("runs.urls")),
    path("api/config-versions/", ConfigVersionListView.as_view(), name="config-versions-list"),
    path(
        "api/config-versions/<int:pk>/publish/",
        ConfigVersionPublishView.as_view(),
        name="config-versions-publish",
    ),
]
