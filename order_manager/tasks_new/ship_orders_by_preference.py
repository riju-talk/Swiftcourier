import logging
import traceback
from django_tasks import task

from account.models import CourierPreferenceSequence, RateCard
from order_manager.tasks_new.ship_orders import ship_orders


logger = logging.getLogger("my-logger")


@task
def ship_orders_by_preference(
    order_ids: list[int],
    hub_id: int,
    user_id: int,
    auto_fetch_courier_preference: bool = True,
    courier_preference: list[int] | None = None,
):
    if not auto_fetch_courier_preference and courier_preference is None:
        raise ValueError(
            "Either auto_fetch_courier_preference must be True or courier_preference must be provided."
        )

    cps = (
        CourierPreferenceSequence.get_user_preference(user_id)
        if auto_fetch_courier_preference
        else courier_preference
    )

    order_need_to_ship = set(order_ids)
    # {order_id: "error_message"}
    errors_encountered = {}

    for c in cps:
        try:
            for oi in order_need_to_ship:
                rate_card = RateCard.objects.filter(user=user_id, courier=c).first()
                res = ship_orders.call(
                    order_ids=[oi],
                    hub_id=hub_id,
                    user_id=user_id,
                    courier_id=c.id,
                    rate_card_id=rate_card.id if rate_card else None,
                )

                if res.get("count", {}).get("success"):
                    order_need_to_ship.remove(oi)
                    if oi in errors_encountered:
                        del errors_encountered[oi]
                else:
                    errors_encountered[oi] = res.get("errors", {}).get(
                        oi, "Unknown error"
                    )
        except Exception as e:
            logger.error(
                f"Error while shipping orders via courier {c}: {traceback.format_exc()}"
            )

    return {
        "shipped_orders": list(set(order_ids) - order_need_to_ship),
        "failed_orders": list(order_need_to_ship),
        "errors": errors_encountered,
    }
