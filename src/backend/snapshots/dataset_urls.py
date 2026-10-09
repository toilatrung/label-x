"""Read-only CVAT project and task selection routes for Snapshot screens."""

from django.urls import path

from snapshots.dataset_views import DatasetListView, DatasetTasksView

urlpatterns = [
    path("", DatasetListView.as_view(), name="datasets-list"),
    path("<int:dataset_id>/tasks/", DatasetTasksView.as_view(), name="datasets-tasks"),
]
