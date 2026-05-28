from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .catalog import catalog_payload, load_catalog
from .engine import configure_objectives, evaluate_tradeoffs


@require_GET
def catalog(_: HttpRequest) -> JsonResponse:
    return JsonResponse(catalog_payload())


@csrf_exempt
@require_POST
def evaluate(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    catalog_data = load_catalog()
    active_objectives = configure_objectives(catalog_data["objectives"], payload.get("objectives"))
    if not active_objectives:
        return JsonResponse({"error": "At least one active objective is required."}, status=400)

    result = evaluate_tradeoffs(
        catalog_data["options"],
        active_objectives,
        filters=payload.get("filters") or {},
        selected_id=payload.get("selectedId"),
        layout_mode=payload.get("layoutMode", "polygon"),
    )
    return JsonResponse(result)


def frontend(_: HttpRequest) -> HttpResponse:
    index_path = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
    if index_path.exists():
        return HttpResponse(index_path.read_text(encoding="utf-8"))
    static_index = Path(settings.BASE_DIR) / "frontend" / "static" / "index.html"
    if static_index.exists():
        return HttpResponse(static_index.read_text(encoding="utf-8"))
    return HttpResponse("<h1>Tradeoff Analytics</h1><p>Frontend assets are missing.</p>")


def frontend_asset(_: HttpRequest, asset_path: str) -> FileResponse:
    assets = {
        "app.js": Path(settings.BASE_DIR) / "frontend" / "static" / "app.js",
        "styles.css": Path(settings.BASE_DIR) / "frontend" / "static" / "styles.css",
        "vendor/react.production.min.js": Path(settings.BASE_DIR)
        / "frontend"
        / "node_modules"
        / "react"
        / "umd"
        / "react.production.min.js",
        "vendor/react-dom.production.min.js": Path(settings.BASE_DIR)
        / "frontend"
        / "node_modules"
        / "react-dom"
        / "umd"
        / "react-dom.production.min.js",
        "vendor/d3.min.js": Path(settings.BASE_DIR) / "frontend" / "node_modules" / "d3" / "dist" / "d3.min.js",
    }
    path = assets.get(asset_path)
    if path is None or not path.exists():
        raise Http404("Asset not found.")
    content_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path.open("rb"), content_type=content_type or "application/octet-stream")
