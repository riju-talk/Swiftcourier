awb_nos = []

orders = Order.objects.filter(awb_number__in=awb_nos)

orders.update(status='delivered')
