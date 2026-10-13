from django.urls import path

from reports.views import EffectivenessReportDetailView

app_name = "reports"

urlpatterns = [path("<int:pk>/", EffectivenessReportDetailView.as_view(), name="detail")]
