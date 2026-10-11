from django.urls import path

from review.rework_views import ReworkCreateView, ReworkSubmittedView, ReworkVerifyView

urlpatterns = [
    path("", ReworkCreateView.as_view(), name="rework-create"),
    path("<int:pk>/submitted/", ReworkSubmittedView.as_view(), name="rework-submitted"),
    path("<int:pk>/verify/", ReworkVerifyView.as_view(), name="rework-verify"),
]
