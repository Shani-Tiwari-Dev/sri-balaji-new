import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sbg.settings")

application = get_wsgi_application()

# Alias so `gunicorn sbg.wsgi:app` and Vercel's Python runtime (which looks
# for a WSGI object named `app`) both work, matching the old Flask entrypoint
# naming (`app.py` exposed `app`).
app = application
