from django.urls import path

from .views import (
    DemoDataView,
    LogsView,
    MigrationsView,
    OverviewView,
    TablesView,
)

urlpatterns = [
    path("overview/", OverviewView.as_view(), name="ops-overview"),
    path("migrations/", MigrationsView.as_view(), name="ops-migrations"),
    path("tables/", TablesView.as_view(), name="ops-tables"),
    path("logs/", LogsView.as_view(), name="ops-logs"),
    path("demo-data/", DemoDataView.as_view(), name="ops-demo-data"),
]
