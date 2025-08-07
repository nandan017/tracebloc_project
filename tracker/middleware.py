# tracker/middleware.py
import traceback
from django.http import HttpResponse

class SimpleTracebackMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        # If an error occurs, return a plain text response
        # with the full traceback.
        return HttpResponse(
            f"<h1>Traceback</h1><pre>{traceback.format_exc()}</pre>",
            content_type="text/html",
            status=500
        )