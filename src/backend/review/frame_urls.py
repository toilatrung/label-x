from django.urls import path

from review.issue_views import FrameCompleteView, FrameIssuesView

urlpatterns = [
    path("<int:pk>/issues/", FrameIssuesView.as_view(), name="frames-issues"),
    path("<int:pk>/complete/", FrameCompleteView.as_view(), name="frames-complete"),
]
