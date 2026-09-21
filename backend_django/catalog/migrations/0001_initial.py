import django.db.models.deletion
from django.db import migrations, models

import catalog.models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Slab",
            fields=[
                ("id", models.CharField(default=catalog.models.gen_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("godown_id", models.CharField(db_index=True, max_length=32)),
                ("godown_name", models.CharField(max_length=120)),
                ("block_number", models.CharField(blank=True, max_length=60, null=True)),
                ("title", models.CharField(max_length=200)),
                ("category", models.CharField(db_index=True, max_length=60)),
                ("image", models.ImageField(blank=True, null=True, upload_to=catalog.models.slab_image_upload_to)),
                ("image_url", models.TextField(blank=True, null=True)),
                ("length", models.FloatField()),
                ("width", models.FloatField()),
                ("unit", models.CharField(default="feet", max_length=20)),
                ("pieces", models.IntegerField(default=1)),
                ("total_sq_ft", models.FloatField(default=0)),
                ("total_sq_meters", models.FloatField(default=0)),
                ("thickness_mm", models.FloatField(blank=True, null=True)),
                ("finish", models.CharField(blank=True, max_length=40, null=True)),
                ("price_per_sq_ft", models.FloatField(default=0)),
                ("is_sold", models.BooleanField(db_index=True, default=False)),
                ("lot_name", models.CharField(blank=True, max_length=120, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "slabs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TrashItem",
            fields=[
                ("id", models.CharField(default=catalog.models.gen_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("slab_snapshot", models.JSONField()),
                ("deleted_at", models.DateTimeField(auto_now_add=True)),
                ("deleted_by", models.CharField(blank=True, max_length=80, null=True)),
                ("expires_at", models.DateTimeField(default=catalog.models.make_trash_expiry)),
            ],
            options={
                "db_table": "trash_items",
                "ordering": ["-deleted_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomerQuery",
            fields=[
                ("id", models.CharField(default=catalog.models.gen_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("order_number", models.CharField(blank=True, max_length=40, null=True)),
                ("client_name", models.CharField(max_length=120)),
                ("mobile_number", models.CharField(max_length=30)),
                ("delivery_address", models.TextField(blank=True, null=True)),
                ("preferred_godown", models.CharField(default="any", max_length=32)),
                ("requirement", models.TextField(blank=True, null=True)),
                ("dimension_unit", models.CharField(default="feet", max_length=20)),
                ("requested_quantity_sqft", models.FloatField(default=0)),
                ("selected_slabs", models.JSONField(default=list)),
                ("total_estimated_cost", models.FloatField(blank=True, null=True)),
                ("status", models.CharField(default="Pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.TextField(blank=True, null=True)),
            ],
            options={
                "db_table": "customer_queries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.CharField(default=catalog.models.gen_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=150)),
                ("message", models.TextField()),
                ("is_active", models.BooleanField(default=True)),
                ("type", models.CharField(default="general", max_length=20)),
                ("date", models.CharField(blank=True, max_length=40, null=True)),
            ],
            options={
                "db_table": "announcements",
            },
        ),
    ]
