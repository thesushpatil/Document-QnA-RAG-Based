from django.urls import path

from . import api, views

urlpatterns = [
    # HTML page (upload + chat UI).
    path("", views.home, name="home"),

    # JSON API (testable without the frontend).
    path("api/documents/", api.DocumentListCreateAPIView.as_view(), name="api-document-list"),
    path("api/documents/<int:pk>/", api.DocumentDetailAPIView.as_view(), name="api-document-detail"),
    path("api/ask/", api.AskAPIView.as_view(), name="api-ask"),
]
