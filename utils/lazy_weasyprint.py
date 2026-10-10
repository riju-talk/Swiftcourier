"""Lazy WeasyPrint imports.

WeasyPrint needs native cairo/pango libs. Importing it at module load crashes
the whole app on hosts without them (e.g. Vercel), even for pages that never
render a PDF. Import on first use instead so only PDF endpoints are affected.
"""


def HTML(*args, **kwargs):
    from weasyprint import HTML as _HTML

    return _HTML(*args, **kwargs)


def FontConfiguration(*args, **kwargs):
    from weasyprint.text.fonts import FontConfiguration as _FontConfiguration

    return _FontConfiguration(*args, **kwargs)
