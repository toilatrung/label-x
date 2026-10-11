from django.urls import path

from review.views import LeaseRenewView

urlpatterns = [path("<int:pk>/renew/", LeaseRenewView.as_view(), name="leases-renew")]
