import logging

from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import CODRemittance

logger = logging.getLogger("cronjob-logger")


User = get_user_model()


def generate_cod_remittance():
    logger.debug(f"Running daily COD remittance task at: {timezone.now()}")

    users = User.objects.filter(is_active=True, role=User.USER).only(
        "id", "email", "cod_remittance_cycle"
    )

    summary = {"created": 0, "skipped": 0}

    for user in users:
        try:
            # Use each user's own remittance cycle (default=3, meaning D+3)
            cutoff_date = timezone.localdate() - timezone.timedelta(
                days=user.cod_remittance_cycle
            )

            logger.debug(
                f"Generating COD remittance for {user.email} "
                f"(cycle=D+{user.cod_remittance_cycle}, cutoff={cutoff_date})"
            )

            obj = CODRemittance.generate_for_user(
                user=user,
                date=cutoff_date,
                logger=logger,
            )
            summary["created" if obj else "skipped"] += 1

        except Exception as e:
            logger.error(f"Error generating COD remittance for user {user.email}: {e}")
            summary["skipped"] += 1

    logger.debug(
        f"Daily COD remittance task completed at: {timezone.now()} | Summary: {summary}"
    )
