from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("order_manager", "0003_shipment_volumetric_weight_kg"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="hsn_code",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
