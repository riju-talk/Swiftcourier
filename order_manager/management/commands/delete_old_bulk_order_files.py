from django.core.management.base import BaseCommand
from order_manager.models import Order

class Command(BaseCommand):
    help = "Delete expired bulk order files (and clear references from orders)."

    def handle(self, *args, **options):
        self.stdout.write("Starting expired bulk order file cleanup...")
        Order.delete_expired_bulk_order_files()
        self.stdout.write(self.style.SUCCESS("Cleanup complete."))
