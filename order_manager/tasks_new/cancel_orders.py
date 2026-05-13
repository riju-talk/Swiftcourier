from django_tasks import task

@task
def cancel_orders(order_ids):
    pass