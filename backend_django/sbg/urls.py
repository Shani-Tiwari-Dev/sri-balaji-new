from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from catalog import frontend_views

urlpatterns = [
    # ---- frontend (plain HTML/CSS/JS, no build step) --------------------
    path("", frontend_views.serve_index),
    path("staff", frontend_views.serve_staff),
    path("staff/", frontend_views.serve_staff),
    path("admin", frontend_views.serve_staff),
    path("admin/", frontend_views.serve_staff),
    # ---- API ----------------------------------------------------------
    path("api/", include("catalog.urls")),
]

# Serve /media/ (uploaded slab photos) ourselves — must come before the
# catch-all frontend route below, or requests for an uploaded photo would
# get handed to serve_static (which only knows about frontend/) and 404.
# Fine for this app's scale; swap for S3 / Supabase Storage + a CDN if
# traffic grows a lot.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    # ---- everything else (about.html, css/*, js/*) -> frontend/ folder --
    path("<path:path>", frontend_views.serve_static),
]
