from django.shortcuts import render


def home(request):
    """Serve the single-page frontend.

    This view holds no business logic. The page talks to the DRF API
    (/api/documents/, /api/ask/) using JavaScript fetch calls, so the
    backend can be tested independently with Postman.
    """
    return render(request, "documents/home.html")
