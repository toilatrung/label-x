from django.urls import path

from review.views import CurrentLeaseView, LeaseRenewView

urlpatterns = [
    path("current/", CurrentLeaseView.as_view(), name="leases-current"),
    path("<int:pk>/renew/", LeaseRenewView.as_view(), name="leases-renew"),
]
