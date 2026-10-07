"""URL patterns cho module GDL.

Endpoint (09-interfaces.tex §api):
  GET /api/guidelines/                          → danh sách guideline versions
  GET /api/guidelines/rules/                    → danh sách rule (có filter)
  GET /api/guidelines/rules/<rule_id>/          → rule theo ID
"""

from django.urls import path

from guideline.views import (
    GuidelineRuleDetailView,
    GuidelineRuleListView,
    GuidelineVersionListView,
)

urlpatterns = [
    path("", GuidelineVersionListView.as_view(), name="guideline-version-list"),
    path("rules/", GuidelineRuleListView.as_view(), name="guideline-rule-list"),
    path("rules/<str:rule_id>/", GuidelineRuleDetailView.as_view(), name="guideline-rule-detail"),
]
