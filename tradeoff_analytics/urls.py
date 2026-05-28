from django.urls import include, path, re_path

from decision.views import frontend, frontend_asset

urlpatterns = [
    path("api/", include("decision.urls")),
    path("assets/<path:asset_path>", frontend_asset, name="frontend-assets"),
    re_path(r"^(?!api/).*$", frontend, name="frontend"),
]
