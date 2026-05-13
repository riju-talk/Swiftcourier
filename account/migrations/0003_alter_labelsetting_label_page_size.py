from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0002_labelsetting_label_page_size"),
    ]

    operations = [
        migrations.AlterField(
            model_name="labelsetting",
            name="label_page_size",
            field=models.CharField(
                choices=[
                    ("a4", "A4"),
                    ("a4_single", "A4 (single label)"),
                    ("4x6", "4x6"),
                    ("3x5", "3x5"),
                ],
                default="4x6",
                max_length=10,
            ),
        ),
    ]
