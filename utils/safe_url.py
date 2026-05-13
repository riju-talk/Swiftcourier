from urllib.parse import urlparse
from django.conf import settings


def is_safe_url(url, allowed_hosts=None):
    """
    Validate that the URL is safe:
    - It's relative (like /dashboard/) OR
    - It belongs to allowed hosts (your own domain)
    """
    if not url:
        return False

    allowed_hosts = allowed_hosts or set(settings.ALLOWED_HOSTS)

    url_info = urlparse(url)

    # If URL has a scheme (http/https) but host is not in allowed_hosts => not safe
    if url_info.scheme and url_info.netloc and url_info.netloc not in allowed_hosts:
        return False

    # If URL is relative (starts with /) and doesn't try to escape (no "//evil.com")
    if url_info.path.startswith("/"):
        return True

    return False
