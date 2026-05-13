import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("my-logger")

class FShipClient:
    def __init__(self, signature: str, base_url: str = "https://capi-qc.fship.in"):
        self.base_url = base_url.rstrip("/")
        self.signature = signature

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "signature": self.signature,
        }

    def _post(self, endpoint: str, payload: Optional[Dict[str, Any]] = None):
        url = f"{self.base_url}{endpoint}"
        response = requests.post(
            url, json=payload or {}, headers=self._headers(), timeout=30
        )
        
        return response.status_code, response.json()

    def _get(self, endpoint: str):
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self._headers(), timeout=30)
        return response.status_code, response.json()

    def get_all_couriers(self):
        return self._get("/api/getallcourier")

    def add_warehouse(self, payload: dict):
        return self._post("/api/addwarehouse", payload)

    def update_warehouse(self, payload: dict):
        return self._post("/api/updatewarehouse", payload)

    def create_forward_order(self, payload: dict):
        return self._post("/api/createforwardorder", payload)

    def cancel_order(self, waybill: str, reason: str = ""):
        payload = {
            "waybill": waybill,
            "reason": reason,
        }
        return self._post("/api/cancelorder", payload)

    def shipping_label(self, waybills: str):
        return self._post("/api/shippinglabel", {"waybill": waybills})

    def shipping_label_by_pickup_id(self, pickup_order_ids: list[int]):
        return self._post(
            "/api/shippinglabelbypickupid", {"pickupOrderId": pickup_order_ids}
        )

    def register_pickup(self, waybills: list[str]):
        return self._post("/api/registerpickup", {"waybills": waybills})

    def tracking_history(self, waybill: str):
        return self._post("/api/trackinghistory", {"waybill": waybill})

    def shipment_summary(self, waybill: str):
        return self._post("/api/shipmentsummary", {"waybill": waybill})

    def rate_calculator(self, payload: dict):
        return self._post("/api/ratecalculator", payload)

    def pincode_serviceability(self, source: str, destination: str):
        payload = {"source_Pincode": source, "destination_Pincode": destination}
        return self._post("/api/pincodeserviceability", payload)

    def reattempt_order(self, payload: dict):
        return self._post("/api/reattemptorder", payload)

    def create_reverse_order(self, payload: dict):
        return self._post("/api/createreverseorder", payload)
