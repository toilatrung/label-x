from django.urls import path

from .dataset_views import DatasetListView, DatasetTasksView

urlpatterns = [
    path("", DatasetListView.as_view(), name="datasets-list"),
    path("<int:id>/tasks/", DatasetTasksView.as_view(), name="datasets-tasks"),
]
