"""
Serves the plain HTML/CSS/JS frontend (no build step) the same way the old
Flask app did with `static_folder=FRONTEND_DIR, static_url_path=""`:
  /            -> frontend/index.html
  /staff /admin -> frontend/staff.html
  /<path>      -> frontend/<path>  (about.html, css/style.css, js/*.js, ...)
"""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


def _safe_path(rel_path: str) -> Path:
    """Resolve rel_path under FRONTEND_DIR, rejecting path traversal."""
    frontend_dir = settings.FRONTEND_DIR.resolve()
    candidate = (frontend_dir / rel_path).resolve()
    if frontend_dir not in candidate.parents and candidate != frontend_dir:
        raise Http404
    if not candidate.is_file():
        raise Http404
    return candidate


def serve_index(request):
    return FileResponse(open(_safe_path("index.html"), "rb"))


def serve_staff(request):
    return FileResponse(open(_safe_path("staff.html"), "rb"))


def serve_static(request, path):
    return FileResponse(open(_safe_path(path), "rb"))
