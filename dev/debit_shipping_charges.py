import uuid

awb_nos = [
    "369163949718",
    "369163952336",
    "369163950462",
    "369163962236",
    "369163955337",
    "369163965886",
    "369163968658",
    "369163967392",
    "369163974246",
    "369163976608",
    "369163984009",
    "369163982777",
    "369163987734",
    "369163988793",
    "369163996132",
    "369164001910",
    "369164005093",
    "369164010639",
    "369164012558",
    "369163825050",
    "369143133984",
    "369143134066",
    "369143093455",
    "369143115690",
    "369143140043",
    "369143139832",
    "369143130969",
    "369143144386",
    "369143129796",
    "369143131553",
    "369143119292",
    "369143140609",
    "369143140982",
    "369143141118",
    "369143127785",
    "369143141460",
    "369143147998",
    "369143142528",
    "369143141934",
    "369143136459",
    "369143148704",
    "369143128300",
    "369143140654",
    "369143128447",
    "369143128553",
    "369143150172",
    "369143128959",
    "369143158130",
    "369143151995",
    "369143166302",
    "369143159243",
    "369143150592",
    "369143158543",
    "369143166456",
    "369143167194",
    "369143170880",
    "369143169235",
    "369143166111",
]

charges = {
    "cod_charge": 0.0,
    "gst_amount": 7.62,
    "base_charge": 42.37,
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
