from django.urls import path

from review.views import QueueNextView, QueueSummaryView

urlpatterns = [
    path("<str:name>/", QueueSummaryView.as_view(), name="queues-summary"),
    path("<str:name>/next/", QueueNextView.as_view(), name="queues-next"),
]
