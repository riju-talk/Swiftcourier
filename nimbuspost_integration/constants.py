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
