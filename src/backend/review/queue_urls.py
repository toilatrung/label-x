from django.urls import path

from review.views import QueueNextView

urlpatterns = [path("<str:name>/next/", QueueNextView.as_view(), name="queues-next")]
