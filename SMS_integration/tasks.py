import logging

from celery import shared_task

from order_manager.models import Order

from .services import process_notification


logger = logging.getLogger("my-logger")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms_notification(
    self, order_id: int, new_status: str, old_status: str | None = None, force: bool = False
):
    try:
        order = (
            Order.objects.select_related(
                "user",
                "shipping_address",
                "shipment",
                "logistic_partner",
            )
            .get(id=order_id)
        )
    except Order.DoesNotExist:
        logger.warning("SMS task: order %s not found", order_id)
        return False

    try:
        success, reason = process_notification(
            order=order,
            status=new_status,
            old_status=old_status,
            force=force,
        )
        return success
    except Exception as exc:
        logger.exception("SMS task failed for order %s", order_id)
        raise self.retry(exc=exc)
