"""Inclua no projeto, por exemplo: path("app/", include("app_update_guard.urls"))."""
from django.urls import path

from .views import DownloadPageView, StatusView, TokenDownloadView

app_name = "app_update_guard"

urlpatterns = [
    path("status/", StatusView.as_view(), name="status"),
    path("download/", DownloadPageView.as_view(), name="download_page"),
    path("download/<str:token>/", TokenDownloadView.as_view(), name="download_token"),
]
