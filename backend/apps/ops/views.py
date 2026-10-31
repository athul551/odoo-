"""Admin-only endpoints behind the developer console (Database page)."""

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOnly

from . import activity, services


class OpsView(APIView):
    """
    Admin-only, and 404 unless ops tools are enabled: a production deployment
    that forgets to turn them off should not advertise a migration runner.
    """

    permission_classes = [IsAdminOnly]

    def initial(self, request, *args, **kwargs):
        if not settings.OPS_TOOLS_ENABLED:
            raise Http404("Ops tools are disabled.")
        super().initial(request, *args, **kwargs)


class OverviewView(OpsView):
    def get(self, request):
        return Response(services.overview())


class MigrationsView(OpsView):
    def get(self, request):
        return Response(services.migration_state())

    def post(self, request):
        return Response(services.apply_migrations(), status=status.HTTP_200_OK)


class TablesView(OpsView):
    def get(self, request):
        return Response({"tables": services.table_stats()})


class LogsView(OpsView):
    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", 100)), activity.MAX_ENTRIES)
        except (TypeError, ValueError):
            limit = 100
        return Response(
            {
                "requests": activity.recent_requests(limit),
                "sql": activity.recent_sql(limit),
                "max_entries": activity.MAX_ENTRIES,
            }
        )

    def delete(self, request):
        activity.clear()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DemoDataView(OpsView):
    def post(self, request):
        return Response(
            services.seed_demo_data(actor=request.user),
            status=status.HTTP_201_CREATED,
        )
