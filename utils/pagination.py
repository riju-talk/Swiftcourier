from django.core.paginator import Paginator, EmptyPage
from django.http import QueryDict
from django.db.models import QuerySet


def paginate_queryset(
    model_obj: QuerySet, data: QueryDict, per_page: int = 10, page_number: int = 1
) -> tuple[Paginator, object]:
    """
    Paginate a Django queryset using request.GET or request.POST data.

    Args:
        model_obj: Django queryset to paginate
        data: request.GET or request.POST
        per_page: fallback per-page value if not provided or invalid
        page_number: fallback page number if not provided or invalid

    Returns:
        (paginator, page_obj)
    """
    try:
        per_page = int(data.get("per_page", per_page))
    except (ValueError, TypeError):
        pass

    try:
        page_number = int(data.get("page", page_number))
    except (ValueError, TypeError):
        pass

    paginator = Paginator(model_obj, per_page)
    try:
        page_obj = paginator.get_page(page_number)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    return paginator, page_obj
