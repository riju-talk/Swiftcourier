from django.core.management.base import BaseCommand
from order_manager.models import Order

class Command(BaseCommand):
    help = "Delete expired or old Barcode which is not required furthr"

    def handle(self, *args, **options):
        self.stdout.write("Starting expired order's barcode file cleanup...")
        count = Order.delete_non_required_barcode()
        self.stdout.write(self.style.SUCCESS(f"Cleanup complete. Cleaned: {count}"))
