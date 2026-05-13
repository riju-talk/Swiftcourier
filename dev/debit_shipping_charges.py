import uuid

awb_nos = [
    "35829512302893",
    "35829512302930",
    "35829512302952",
    "35829512302974",
    "35829512302355",
    "35829512302370",
    "35829512302392",
    "35829512302414",
    "35829512302436",
    "35829512302451",
    "35829512302473",
    "35829512302495",
    "35829512302510",
    "35829512302532",
    "35829512302554",
    "35829512302576",
    "35829512302591",
    "35829512302613",
    "35829512302635",
    "35829512302650",
    "35829512302672",
    "35829512302683",
    "35829512302716",
    "35829512302720",
    "35829512302786",
    "35829512302823",
    "35829512302856",
    "35829512302926",
    "35829512302941",
    "35829512302963",
    "35829512302985",
]

charges = {
    "cod_charge": 0.0,
    "gst_amount": 8.28,
    "base_charge": 46.0,
    "rto_charges": 1.18,
    "rto_gst_amount": 0.18,
    "rto_base_charge": 1.0,
    "additional_charges": 0.0,
    "rto_additional_charge": 0.0,
}
total_shipping_charges = charges["base_charge"] + charges["gst_amount"]

o = Order.objects.filter(awb_number__in=awb_nos)

for i in o:
    trx_amount = i.payment.shipping_charges
    trsn = Transaction.create_transaction(
        user=i.user,
        merchant_txn_id=str(i.id) + "_" + str(uuid.uuid4()),
        amount_rs=total_shipping_charges,
        desc="shipping_charges",
        transaction_type="debit",
    )
    trsn.debit(awb_number=i.awb_number)
    i.payment.shipping_charges = total_shipping_charges
    i.payment.price_breakup = charges
    i.payment.save()
