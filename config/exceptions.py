import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """DRF exception handler — catches APIExceptions normally, wraps everything else in JSON."""
    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception in %s", context.get("view"))
        response = Response(
            {"error": str(exc) or "An unexpected error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        response.accepted_renderer = context["request"].accepted_renderer
        response.accepted_media_type = context["request"].accepted_media_type
        response.renderer_context = context

    return response


def handler500(request, *args, **kwargs):
    """Fallback for exceptions that escape DRF entirely (e.g. middleware errors)."""
    return JsonResponse({"error": "Internal server error."}, status=500)
