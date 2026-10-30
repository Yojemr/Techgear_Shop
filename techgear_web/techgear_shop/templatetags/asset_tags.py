"""URLs de recursos locales que cambian cuando se modifica su contenido."""

from hashlib import sha256
from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def asset_url(path):
    """Evita reutilizar CSS, JavaScript o iconos anteriores tras una actualización."""
    url = static(path)
    source = finders.find(path)
    if source is None:
        return url
    try:
        # La versión depende del contenido; una recarga normal conserva la caché
        # de los archivos que no cambiaron y descarga los que sí fueron editados.
        version = sha256(Path(source).read_bytes()).hexdigest()[:12]
    except OSError:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={version}"
