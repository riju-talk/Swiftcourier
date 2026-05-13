# Status mapping dictionary
from datetime import datetime
import logging

import pandas as pd


STATUS_MAPPING = {
    "pp": "pending_pickup",
    "pending pickup": "pending_pickup",
    "ready": "ready_to_ship",
    "rto": "rto",
    "delivered": "delivered",
}

logger = logging.getLogger("my-logger")


def _serialize_cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def validate_and_process_bulk_orders(file, user) -> tuple[list, list, list, list]:
    """Process bulk orders from CSV/Excel file"""
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        elif file.name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(file)
        else:
            return [], ["Invalid file format. Only CSV and Excel files are allowed."], [], []
    except Exception as e:
        return [], ["Error reading uploaded file"], [], []

    errors = []
    success_count = 0
    orders_data = []
    original_headers = [str(col) for col in df.columns]
    failed_rows = []

    for idx, row in enumerate(df.to_dict(orient="records")):
        row_errors = []
        order_data = {}

        # Convert row to dictionary with cleaned keys (strip *, lowercase, snake_case)
        row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        original_row = {str(k): _serialize_cell(v) for k, v in row.items()}
        row_dict = {
            k.strip().lower().replace(" ", "_").replace("*", ""): v
            for k, v in row.items()
        }

        # Basic validations
        required_fields = [
            "order_id",
            "payment_type",
            "first_name",
            "address_1",
            "mobile",
            "pincode",
            "city",
            "state",
            "country",
            "weight(kg)",
            "length(cm)",
            "breadth(cm)",
            "height(cm)",
        ]

        for field in required_fields:
            if not row_dict.get(field):
                row_errors.append(f"Row {idx + 1}: Missing required field - {field}")

        # Validate numeric dimensions and weight
        numeric_fields = [
            "weight(kg)",
            "length(cm)",
            "breadth(cm)",
            "height(cm)",
        ]
        for field in numeric_fields:
            val = row_dict.get(field)
            if val is not None:
                try:
                    num_val = float(val)
                    if num_val <= 0:
                        row_errors.append(f"Row {idx + 1}: {field} must be positive")
                except (ValueError, TypeError):
                    row_errors.append(f"Row {idx + 1}: Invalid value for {field}")
            else:
                row_errors.append(f"Row {idx + 1}: Missing required field - {field}")

        # Validate Product 1 (required)
        product_count = 0
        i = 1
        sku = row_dict.get(f"sku({i})")
        product_fields = [
            f"sku({i})",
            f"product({i})",
            f"quantity({i})",
            f"per_product_price({i})",
            f"total_price({i})",
        ]

        product_count += 1
        for p_field in product_fields:
            if not row_dict.get(p_field) and not p_field.startswith("sku"):
                row_errors.append(
                    f"Row {idx + 1}: Missing Product's {i} field - {p_field}"
                )

        # Validate quantity
        try:
            quantity = int(row_dict[f"quantity({i})"])
            if quantity < 1:
                row_errors.append(f"Row {idx + 1}: Product {i} quantity must be ≥1")
        except (ValueError, TypeError):
            row_errors.append(f"Row {idx + 1}: Invalid Product {i} quantity")

        # Validate price calculation
        try:
            price = float(row_dict[f"per_product_price({i})"])
            total = float(row_dict[f"total_price({i})"])
            if not round(price * quantity, 2) == round(total, 2):
                row_errors.append(
                    f"Row {idx + 1}: Product {i} total price mismatch"
                )
        except (ValueError, TypeError):
            row_errors.append(f"Row {idx + 1}: Invalid Product {i} pricing")

        # Validate additional products (2-10)
        for i in range(2, 11):
            # sku = row_dict.get(f"sku({i})")
            # if sku:
            product_count += 1
            # Check all product fields exist
            product_fields = [
                f"sku({i})",
                f"product({i})",
                f"quantity({i})",
                f"per_product_price({i})",
                f"total_price({i})",
            ]
            for p_field in product_fields:
                if not row_dict.get(p_field) and not p_field.startswith("sku"):
                    break
            else:
                # Validate quantity
                try:
                    quantity = int(row_dict[f"quantity({i})"])
                    if quantity < 1:
                        row_errors.append(
                            f"Row {idx + 1}: Product {i} quantity must be ≥1"
                        )
                except (ValueError, TypeError):
                    row_errors.append(f"Row {idx + 1}: Invalid Product {i} quantity")

                # Validate price calculation
                try:
                    price = float(row_dict[f"per_product_price({i})"])
                    total = float(row_dict[f"total_price({i})"])
                    if not round(price * quantity, 2) == round(total, 2):
                        row_errors.append(
                            f"Row {idx + 1}: Product {i} total price mismatch"
                        )
                except (ValueError, TypeError):
                    row_errors.append(f"Row {idx + 1}: Invalid Product {i} pricing")

        # Validate COD amount
        payment_type = (row_dict.get("payment_type") or "").lower()
        if payment_type == "pp":
            payment_type = "prepaid"

        if payment_type == "cod":
            cod_amount = row_dict.get("cod_collectable_amount")
            if cod_amount is None:
                row_errors.append(
                    f"Row {idx + 1}: COD Collectable Amount required for COD payments"
                )
            else:
                try:
                    cod_amount_val = float(cod_amount)
                    if cod_amount_val <= 0:
                        row_errors.append(
                            f"Row {idx + 1}: COD Collectable Amount must be >0"
                        )
                except (ValueError, TypeError):
                    row_errors.append(f"Row {idx + 1}: Invalid COD Collectable Amount")
        elif payment_type not in ["cod", "prepaid"]:
            row_errors.append(
                f"Row {idx + 1}: Invalid Payment Type - must be COD/Prepaid"
            )

        if row_errors:
            errors.extend(row_errors)
            failed_rows.append(
                {
                    "row_number": idx + 1,
                    "row_data": original_row,
                    "reason": " | ".join(row_errors),
                    "reasons": row_errors,
                }
            )
            continue

        order_date = row_dict.get("order_date_(dd-mm-yyyy)")
        if order_date is not None:
            try:
                order_date = datetime.strptime(order_date, "%d-%m-%Y").date()
            except ValueError:
                order_date = datetime.now()

        # Prepare order data
        try:
            order_data = {
                "user": user,
                "order_id": row_dict["order_id"],
                "order_date": order_date,
                "payment_type": payment_type,
                "cod_collectable_amount": float(row_dict.get("cod_collectable_amount") or 0),
                "first_name": row_dict["first_name"],
                "last_name": row_dict.get("last_name"),
                "email": row_dict.get("email"),
                "company_name": row_dict.get("company_name"),
                "address_1": row_dict["address_1"],
                "address_2": row_dict.get("address_2"),
                "landmark": row_dict.get("landmark"),
                "mobile": row_dict["mobile"],
                "alternate_phone": row_dict.get("alternate_phone"),
                "pincode": row_dict["pincode"],
                "city": row_dict["city"],
                "state": row_dict["state"],
                "country": row_dict["country"],
                "weight": float(row_dict.get("weight(kg)") or 0),
                "length": float(row_dict.get("length(cm)") or 0),
                "breadth": float(row_dict.get("breadth(cm)") or 0),
                "height": float(row_dict.get("height(cm)") or 0),
                "shipping_charges": float(row_dict.get("shipping_charges") or 0),
                "cod_charges": float(row_dict.get("cod_charges") or 0),
                "discount": float(row_dict.get("discount") or 0),
                "products": [],
                "_source_row": original_row,
                "_row_number": idx + 1,
            }

            # Add Product 1 (validated)
            i = 1
            order_data["products"].append(
                {
                    "sku": row_dict[f"sku({i})"],
                    "name": row_dict[f"product({i})"],
                    "quantity": int(row_dict.get(f"quantity({i})") or 0),
                    "price": float(row_dict.get(f"per_product_price({i})") or 0),
                    "total": float(row_dict.get(f"total_price({i})") or 0),
                }
            )

            # Add additional products (2-10) if present
            for i in range(2, 11):
                try:
                    sku = row_dict.get(f"sku({i})")
                    product_name = row_dict[f"product({i})"]
                    if sku or product_name:
                        order_data["products"].append(
                            {
                                "sku": sku,
                                "name": product_name,
                                "quantity": int(row_dict.get(f"quantity({i})") or 0),
                                "price": float(
                                    row_dict.get(f"per_product_price({i})") or 0
                                ),
                                "total": float(row_dict.get(f"total_price({i})") or 0),
                            }
                        )
                except:
                    pass

            orders_data.append(order_data)
            success_count += 1

        except KeyError as e:
            column = e.args[0]
            error_msg = f"Row {idx + 1}: Missing required column '{column}'"
            errors.append(error_msg)
            failed_rows.append(
                {
                    "row_number": idx + 1,
                    "row_data": original_row,
                    "reason": error_msg,
                    "reasons": [error_msg],
                }
            )
        except ValueError as e:
            if "could not convert" in str(e):
                field = "unknown_field"
                # Map error to likely column based on common patterns
                if "weight" in str(e):
                    field = "weight(kg)"
                elif "length" in str(e):
                    field = "length(cm)"
                elif "breadth" in str(e):
                    field = "breadth(cm)"
                elif "height" in str(e):
                    field = "height(cm)"
                error_msg = f"Row {idx + 1}: Invalid numeric value in column '{field}'"
            else:
                error_msg = f"Row {idx + 1}: Value error - {str(e)}"
            errors.append(error_msg)
            failed_rows.append(
                {
                    "row_number": idx + 1,
                    "row_data": original_row,
                    "reason": error_msg,
                    "reasons": [error_msg],
                }
            )

        except Exception as e:
            error_msg = f"Row {idx + 1}: Error processing order data"
            errors.append(error_msg)
            failed_rows.append(
                {
                    "row_number": idx + 1,
                    "row_data": original_row,
                    "reason": error_msg,
                    "reasons": [error_msg],
                }
            )

    return orders_data, errors, original_headers, failed_rows
