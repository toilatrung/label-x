"""URL routes cho module GDL."""

from django.urls import path

from guideline.views import GuidelineRuleDetailView, GuidelineRuleListView

urlpatterns = [
    path("rules/", GuidelineRuleListView.as_view(), name="guidelines-rules-list"),
    path(
        "rules/<str:rule_id>/",
        GuidelineRuleDetailView.as_view(),
        name="guidelines-rules-retrieve",
    ),
]
