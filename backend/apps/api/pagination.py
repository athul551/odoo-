from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Bounded pages: a client can ask for more, never for everything."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200
