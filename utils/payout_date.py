from datetime import timedelta
from django.conf import settings


def get_next_payout_date(current_date):
    """
    Returns the earliest upcoming payout date from COD_PAYOUT_DAYS.
    If today is a payout day, it returns today.
    """
    payout_days = getattr(settings, "COD_PAYOUT_DAYS", [1, 4])  # default Tue + Fri

    nearest = None
    for payout_day in payout_days:
        diff = (payout_day - current_date.weekday()) % 7
        candidate = current_date + timedelta(days=diff)

        if nearest is None or candidate < nearest:
            nearest = candidate

    return nearest
