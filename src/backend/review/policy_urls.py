from django.urls import path

from review.policy_views import ReviewPolicyView

urlpatterns = [path("", ReviewPolicyView.as_view(), name="review-policy")]
