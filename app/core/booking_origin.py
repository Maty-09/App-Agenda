from urllib.parse import urlsplit


ORIGEN_AGENDA_WEB = "Agenda directa desde web"


def normalizar_origen_web(value: str | None) -> str | None:
    """Return only the HTTP(S) origin, never paths, query strings, or credentials."""
    if not value:
        return None

    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        return None

    hostname = hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port else hostname
    return f"{parsed.scheme.lower()}://{netloc}"
