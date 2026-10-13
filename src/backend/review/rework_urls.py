from django.urls import path

from review.rework_read_views import (
    ReworkCollectionView,
    ReworkCurrentRevisionView,
    ReworkDetailView,
)
from review.rework_views import ReworkSubmittedView, ReworkVerifyView

urlpatterns = [
    path("", ReworkCollectionView.as_view(), name="rework-create"),
    path("<int:pk>/", ReworkDetailView.as_view(), name="rework-detail"),
    path(
        "<int:pk>/current-revision/",
        ReworkCurrentRevisionView.as_view(),
        name="rework-current-revision",
    ),
    path("<int:pk>/submitted/", ReworkSubmittedView.as_view(), name="rework-submitted"),
    path("<int:pk>/verify/", ReworkVerifyView.as_view(), name="rework-verify"),
]
