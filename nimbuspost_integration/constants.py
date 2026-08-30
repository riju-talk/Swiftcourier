# NimbusPost webhook payload, confirmed straight from their partner
# dashboard's "Webhooks" help panel (Settings -> Webhooks -> the info panel
# next to the webhook form), sample payload:
#
#   {
#       "awb_number": "4152912381315",
#       "status": "in transit",
#       "event_time": "2021-02-26 16:19:59",
#       "location": "Delhi",
#       "message": "Reached at nearest hub",
#       "rto_awb": ""
#   }
#
# Only "in transit" is a CONFIRMED real status value (from that same sample).
# Everything else below is a best-effort guess following the same
# lowercase-with-spaces convention, not verified against a real payload -
# an unmapped status is logged clearly (see views.py) rather than silently
# dropped, so real values can be added here as they show up in the logs.
STATUS_MAPPING = {
    "in transit": "in_transit",
    "pending pickup": "pending_pickup",
    "picked up": "in_transit",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "undelivered": "ndr",
    "cancelled": "ready_to_ship",
    "rto": "rto",
    "rto in transit": "rto_in_transit",
    "rto delivered": "rto_delivered",
    "lost": "lost",
    "damaged": "damaged",
}

AWB_FIELD = "awb_number"
STATUS_FIELD = "status"


# --- Outbound API (partner API, https://documenter.getpostman.com/view/9692837/TW6wHnoz) ---
# NimbusPost runs the same shipping platform as Xpressbees, so the endpoint
# surface mirrors xpressbees_integration.xpressbees almost exactly - only the
# base URL and a couple of path segments differ.
BASE_URL = "https://api.nimbuspost.com/v1"

# Seconds to wait on any single NimbusPost HTTP call before giving up. Their
# create-shipment call in particular can be slow (courier allocation happens
# inline), hence the generous ceiling.
REQUEST_TIMEOUT = 30

# How many times nimbuspost_request() will transparently re-login and retry
# after NimbusPost rejects the bearer token.
MAX_AUTH_RETRIES = 2

# Raw NimbusPost login-response / API-response messages that mean "your token
# is missing or expired" - matched case-insensitively as substrings.
AUTH_FAILURE_HINTS = ("token", "unauthenticated", "unauthorized")
