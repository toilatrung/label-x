from django.urls import path

from snapshots.views import SnapshotCollectionView, SnapshotDetailView

urlpatterns = [
    path("", SnapshotCollectionView.as_view(), name="snapshots-list-create"),
    path("<int:pk>/", SnapshotDetailView.as_view(), name="snapshots-retrieve"),
]
