from django.urls import path

from .dataset_views import DatasetListView, DatasetTasksView
from .summary_views import DatasetRevisionsView, DatasetSummaryView

urlpatterns = [
    path("summary/", DatasetSummaryView.as_view(), name="datasets-summary"),
    path("<int:id>/revisions/", DatasetRevisionsView.as_view(), name="datasets-revisions"),
    path("", DatasetListView.as_view(), name="datasets-list"),
    path("<int:id>/tasks/", DatasetTasksView.as_view(), name="datasets-tasks"),
]
