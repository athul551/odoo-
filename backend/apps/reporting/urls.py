from django.urls import path

from .views import ChaseListView, SummaryView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="reporting-summary"),
    path("chase/", ChaseListView.as_view(), name="reporting-chase"),
]
