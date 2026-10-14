from django.urls import path

from snapshots.summary_views import SnapshotRunsView
from snapshots.views import SnapshotCollectionView, SnapshotDetailView

urlpatterns = [
    path("<int:pk>/runs/", SnapshotRunsView.as_view(), name="snapshots-runs"),
    path("", SnapshotCollectionView.as_view(), name="snapshots-list-create"),
    path("<int:pk>/", SnapshotDetailView.as_view(), name="snapshots-retrieve"),
]
