import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from account.models import Courier as AccountCourier
from account.models import RateCard as UserRateCard
from order_manager.models import Hub


logger = logging.getLogger("my-logger")


PINCODE_RE = re.compile(r"^\d{6}$")

AGGREGATOR_ALIASES = {
    "fship": "Fship",
    "rapidshyp": "RapidShyp",
    "rapidshyp new": "RapidShyp New",
    "rapidshyp_new": "RapidShyp New",
}


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def get_warehouses(request):
    user = _get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    hubs = (
        Hub.objects.filter(user=user, is_active=True)
        .values("id", "name", "pin_code", "city")
        .order_by("name")
    )

    payload = [
        {
            "hub_id": hub["id"],
            "warehouse_id": hub["id"],
            "name": hub["name"],
            "pincode": hub["pin_code"],
            "city": hub["city"],
        }
        for hub in hubs
    ]
    return JsonResponse({"warehouses": payload})


@require_GET
async def check_serviceability(request):
    user = _get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    pickup = (request.GET.get("pickup_pincode") or "").strip()
    destination = (request.GET.get("destination_pincode") or "").strip()
    hub_id = (request.GET.get("hub_id") or request.GET.get("warehouse_id") or "").strip()

    if hub_id:
        pickup = await _resolve_hub_pincode(hub_id, user)
        if not pickup:
            return JsonResponse(
                {"serviceable_couriers": [], "error": "Invalid hub_id"},
                status=422,
            )

    if not pickup:
        return JsonResponse(
            {"detail": "Either pickup_pincode or hub_id must be provided"},
            status=422,
        )

    if not _is_valid_pincode(pickup) or not _is_valid_pincode(destination):
        return JsonResponse(
            {"detail": "Pincodes must be 6 digits"},
            status=422,
        )

    ratecards = await sync_to_async(list)(
        UserRateCard.objects.filter(user=user).select_related("courier")
    )
    if not ratecards:
        return JsonResponse(
            {
                "serviceable_couriers": [],
                "pickup_pincode": pickup,
                "destination_pincode": destination,
                "error": "No rate cards configured for this user",
            }
        )

    aggregator_couriers, ratecard_map = _build_ratecard_map(ratecards)
    results = await _fetch_from_aggregators(pickup, destination, aggregator_couriers)
    logger.debug(f"Result of servicability: {results}")

    serviceable: List[dict] = []
    for result in results:
        if not isinstance(result, dict) or result.get("error"):
            continue
        agg_label = _normalize_aggregator(result.get("aggregator", ""))
        if not agg_label:
            continue

        for courier in result.get("couriers", []):
            if not courier.get("serviceable", True):
                continue

            ratecard = _find_ratecard(ratecard_map, agg_label, courier)
            if not ratecard:
                continue

            serviceable.append(
                {
                    "name": ratecard.courier.name,
                    "aggregator": agg_label,
                    "eta": courier.get("eta") or courier.get("estimated_days"),
                    "type": courier.get("type") or _ratecard_primary_mode(ratecard),
                    "courier_code": courier.get("courier_code")
                    or ratecard.courier.abbreviation,
                    "courier_id": ratecard.courier.id,
                    "cod": _ratecard_supports_cod(ratecard),
                }
            )

    return JsonResponse(
        {
            "serviceable_couriers": serviceable,
            "pickup_pincode": pickup,
            "destination_pincode": destination,
        }
    )


@require_GET
def dashboard_data(request):
    user = _get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    ratecards = list(UserRateCard.objects.filter(user=user).select_related("courier"))
    active_couriers = len({rc.courier_id for rc in ratecards if rc.courier_id})
    pincodes_covered = (
        Hub.objects.filter(user=user, is_active=True)
        .values("pin_code")
        .distinct()
        .count()
    )
    cod_available = sum(1 for rc in ratecards if _ratecard_supports_cod(rc))

    return JsonResponse(
        {
            "active_couriers": active_couriers,
            "pincodes_covered": pincodes_covered,
            "cod_available": cod_available,
            "ndd_zones": 0,
        }
    )


def _get_authenticated_user(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user
    return None


def _is_valid_pincode(value: str) -> bool:
    return bool(PINCODE_RE.match(value or ""))


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _normalize_aggregator(value: str) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return AGGREGATOR_ALIASES.get(normalized)


def _detect_aggregator(courier: AccountCourier) -> Optional[str]:
    abbr = (getattr(courier, "abbreviation", "") or "").strip().lower()
    integration_path = (
        (getattr(courier, "integration_path", "") or "").strip().lower()
    )

    if "rapidshyp_new_integration" in integration_path or abbr.startswith("rsn"):
        return "RapidShyp New"
    if "rapidshyp_integration" in integration_path or abbr.startswith("rs"):
        return "RapidShyp"
    if "fship_integration" in integration_path or abbr.startswith("fs"):
        return "Fship"
    return None


def _courier_keys_for_ratecard(ratecard: UserRateCard) -> List[str]:
    courier = ratecard.courier
    if not courier:
        return []

    keys = set()
    for value in [courier.name, courier.abbreviation]:
        normalized = _normalize_name(value)
        if normalized:
            keys.add(normalized)
    return sorted(keys)


def _courier_keys_from_result(payload: dict) -> List[str]:
    keys = set()
    for field in ["name", "courier_name", "courier", "courier_code", "code"]:
        normalized = _normalize_name(str(payload.get(field, "")))
        if normalized:
            keys.add(normalized)
    return sorted(keys)


def _find_ratecard(
    ratecard_map: Dict[Tuple[str, str], UserRateCard],
    agg_label: str,
    courier_payload: dict,
) -> Optional[UserRateCard]:
    for key in _courier_keys_from_result(courier_payload):
        ratecard = ratecard_map.get((agg_label, key))
        if ratecard:
            return ratecard
    return None


def _build_ratecard_map(
    ratecards: List[UserRateCard],
) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], UserRateCard]]:
    aggregator_couriers: Dict[str, set] = {}
    ratecard_map: Dict[Tuple[str, str], UserRateCard] = {}

    for ratecard in ratecards:
        courier = ratecard.courier
        if not courier:
            continue
        agg_label = _detect_aggregator(courier)
        if not agg_label:
            continue

        aggregator_couriers.setdefault(agg_label, set()).add(courier.name)
        for key in _courier_keys_for_ratecard(ratecard):
            ratecard_map[(agg_label, key)] = ratecard

    return (
        {key: sorted(values) for key, values in aggregator_couriers.items()},
        ratecard_map,
    )


def _ratecard_supports_cod(ratecard: UserRateCard) -> bool:
    data = ratecard.data or {}
    for mode_data in data.values():
        for weight_data in mode_data.values():
            for additional_data in weight_data.values():
                for zone_data in additional_data.values():
                    for flow_data in zone_data.values():
                        cod_charge = flow_data.get("cod_charges", 0) or 0
                        cod_percent = flow_data.get("cod_percentage", 0) or 0
                        if cod_charge or cod_percent:
                            return True
    return False


def _ratecard_primary_mode(ratecard: UserRateCard) -> str:
    try:
        modes = ratecard.get_available_modes()
        return modes[0] if modes else ""
    except Exception:
        return ""


async def _resolve_hub_pincode(hub_id: str, user) -> Optional[str]:
    try:
        hub_id_int = int(hub_id)
    except (TypeError, ValueError):
        return None

    hub = await sync_to_async(
        lambda: Hub.objects.filter(user=user, id=hub_id_int, is_active=True)
        .values("pin_code")
        .first()
    )()

    if not hub:
        return None
    return hub.get("pin_code")


def _safe_import_aggregators() -> Dict[str, object]:
    """Serviceability adapters live in ``serviceability.aggregators`` so this
    feature never imports the shipping-critical ``*_integration.common`` modules
    directly (they only borrow the low-level request helper)."""
    modules: Dict[str, object] = {}
    try:
        from serviceability.aggregators import fship as fship_agg

        modules["Fship"] = fship_agg
    except Exception as exc:
        logger.warning("Fship aggregator import failed: %s", exc)

    try:
        from serviceability.aggregators import rapidshyp as rapidshyp_agg

        modules["RapidShyp"] = rapidshyp_agg
    except Exception as exc:
        logger.warning("RapidShyp aggregator import failed: %s", exc)

    try:
        from serviceability.aggregators import rapidshyp_new as rapidshyp_new_agg

        modules["RapidShyp New"] = rapidshyp_new_agg
    except Exception as exc:
        logger.warning("RapidShyp New aggregator import failed: %s", exc)

    return modules


async def _fetch_from_aggregators(
    pickup: str,
    destination: str,
    aggregator_couriers: Dict[str, List[str]],
) -> List[dict]:
    modules = _safe_import_aggregators()
    tasks = []
    for agg_label, couriers in aggregator_couriers.items():
        module = modules.get(agg_label)
        if not module:
            logger.warning("Aggregator module missing for %s", agg_label)
            continue
        tasks.append(
            _call_aggregator(
                module,
                agg_label,
                pickup,
                destination,
                couriers,
            )
        )

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    normalized_results = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Aggregator request failed: %s", result)
            continue
        normalized_results.append(result)
    return normalized_results


async def _call_aggregator(
    module: object,
    agg_label: str,
    pickup: str,
    destination: str,
    couriers: List[str],
) -> dict:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                module.check_serviceability,
                pickup_pincode=pickup,
                destination_pincode=destination,
                couriers=couriers,
            ),
            timeout=2.5,
        )
    except asyncio.TimeoutError:
        logger.warning("Aggregator %s timed out", agg_label)
        return {"aggregator": agg_label, "couriers": [], "error": "timeout"}
    except Exception as exc:
        logger.warning("Aggregator %s failed: %s", agg_label, exc)
        return {"aggregator": agg_label, "couriers": [], "error": "failed"}

    if not isinstance(result, dict):
        return {"aggregator": agg_label, "couriers": [], "error": "invalid"}

    result.setdefault("aggregator", agg_label)
    result.setdefault("couriers", [])
    return result
