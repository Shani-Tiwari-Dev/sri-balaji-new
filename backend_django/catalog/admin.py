# The staff-facing management UI is frontend/staff.html (its own login +
# dashboard, calling the /api/... endpoints in catalog/views.py). Django's
# built-in /django-admin/ site isn't wired up by default to keep this app
# lean; add `path("django-admin/", admin.site.urls)` to sbg/urls.py and
# register models here if you also want Django's generic admin UI.
