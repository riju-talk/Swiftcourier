"""RapidShyp New serviceability adapter.

Identical wire format to the RapidShyp adapter, but authenticated through
``rapidshyp_new_integration.common.rapidshyp_request``.
"""

import logging

from rapidshyp_new_integration.common import rapidshyp_request as _rapidshyp_new_request

from serviceability.aggregators.rapidshyp import (
    _extract_serviceability_items,  # noqa: F401  (re-exported for parity)
    _normalize_name,  # noqa: F401
)
from serviceability.aggregators.rapidshyp import check_serviceability as _rs_check

logger = logging.getLogger("my-logger")


def _serviceability_request(payload: dict):
    response = _rapidshyp_new_request("POST", payload, "/serviceabilty_check")
    if response.status_code == 404:
        response = _rapidshyp_new_request("POST", payload, "/serviceability_check")
    return response


def check_serviceability(pickup_pincode, destination_pincode, couriers=None, **kwargs):
    return _rs_check(
        pickup_pincode,
        destination_pincode,
        couriers=couriers,
        rs_request=_serviceability_request,
        _aggregator_label="RapidShyp New",
    )
