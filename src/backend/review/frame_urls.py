from django.urls import path

from review.issue_views import FrameCompleteView, FrameIssuesView, FrameWorkspaceView

urlpatterns = [
    path("<int:pk>/issues/", FrameIssuesView.as_view(), name="frames-issues"),
    path("<int:pk>/workspace/", FrameWorkspaceView.as_view(), name="frames-workspace"),
    path("<int:pk>/complete/", FrameCompleteView.as_view(), name="frames-complete"),
]
