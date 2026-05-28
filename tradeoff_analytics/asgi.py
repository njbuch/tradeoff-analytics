"""ASGI config for tradeoff_analytics."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tradeoff_analytics.settings")

application = get_asgi_application()
