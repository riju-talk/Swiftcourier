from django.conf import settings


def clean_aggregator_or_courier_name(name: str | None) -> str | None:
    if name is None:
        return None

    for text in settings.AGGREGATOR_BLACKLISTED_TEXTS:
        name = name.replace(text, "")
    return name.strip()
