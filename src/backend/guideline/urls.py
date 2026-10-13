"""URL routes cho module GDL."""

from django.urls import path

from guideline.views import (
    GuidelineMappingListView,
    GuidelineRuleDetailView,
    GuidelineRuleListView,
    GuidelineVersionsListView,
)

urlpatterns = [
    path("versions/", GuidelineVersionsListView.as_view(), name="guidelines-versions-list"),
    path("mappings/", GuidelineMappingListView.as_view(), name="guidelines-mappings-list"),
    path("rules/", GuidelineRuleListView.as_view(), name="guidelines-rules-list"),
    path(
        "rules/<str:rule_id>/",
        GuidelineRuleDetailView.as_view(),
        name="guidelines-rules-retrieve",
    ),
]
