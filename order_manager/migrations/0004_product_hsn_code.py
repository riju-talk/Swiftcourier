from django.db import migrations, models


class Migration(migrations.Migration):
    """Historically this and 0006_product_hsn_code BOTH added Product.hsn_code on
    divergent branches, then 0007 merged them. Applied linearly against a fresh
    database the second AddField errors with "column already exists" (SQLite
    tolerated the old ordering; PostgreSQL does not).

    Fix: keep the migration-graph *state* operation so project state stays
    correct, but drop the *database* operation. 0006_product_hsn_code issues the
    real ADD COLUMN; whichever of the two the planner runs first creates it, the
    other is a state-only no-op, and 0008 settles the column's final definition.
    """

    dependencies = [
        ("order_manager", "0003_shipment_volumetric_weight_kg"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="product",
                    name="hsn_code",
                    field=models.CharField(blank=True, default="", max_length=32),
                ),
            ],
            database_operations=[],
        ),
    ]
