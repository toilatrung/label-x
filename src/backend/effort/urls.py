from django.urls import path

from effort.views import EffortEventCollectionView

urlpatterns = [path("", EffortEventCollectionView.as_view(), name="effort-events-create")]
