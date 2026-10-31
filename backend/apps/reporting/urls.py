from django.urls import path

from .views import ChaseListView, ExpiringListView, SummaryView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="reporting-summary"),
    path("chase/", ChaseListView.as_view(), name="reporting-chase"),
    path("expiring/", ExpiringListView.as_view(), name="reporting-expiring"),
]
