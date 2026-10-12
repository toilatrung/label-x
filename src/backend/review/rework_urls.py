from django.urls import path

from review.rework_read_views import ReworkDetailView, rework_collection
from review.rework_views import ReworkSubmittedView, ReworkVerifyView

urlpatterns = [
    path("", rework_collection, name="rework-create"),
    path("<int:pk>/", ReworkDetailView.as_view(), name="rework-detail"),
    path("<int:pk>/submitted/", ReworkSubmittedView.as_view(), name="rework-submitted"),
    path("<int:pk>/verify/", ReworkVerifyView.as_view(), name="rework-verify"),
]
