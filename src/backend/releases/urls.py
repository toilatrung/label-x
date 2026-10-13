from django.urls import path

from releases.views import ReleaseApproveView, ReleaseListView, ReleaseManifestView

app_name = "releases"

urlpatterns = [
    path("", ReleaseListView.as_view(), name="list"),
    path("<int:pk>/manifest/", ReleaseManifestView.as_view(), name="manifest"),
    path("<int:pk>/approve/", ReleaseApproveView.as_view(), name="approve"),
]
