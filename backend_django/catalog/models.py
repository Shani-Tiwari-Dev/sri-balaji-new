import uuid
from datetime import datetime, timedelta, timezone

from django.db import models

TRASH_RETENTION_DAYS = 7


def gen_id():
    return uuid.uuid4().hex


def utcnow():
    return datetime.now(timezone.utc)


def iso_z(dt):
    """Format an aware datetime as e.g. 2026-09-13T10:00:00Z."""
    if dt is None:
        return None
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def make_trash_expiry():
    return utcnow() + timedelta(days=TRASH_RETENTION_DAYS)


def slab_image_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"slabs/{gen_id()}.{ext}"


class Slab(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=gen_id, editable=False)
    godown_id = models.CharField(max_length=32, db_index=True)  # godown_1 / godown_2 / godown_3
    godown_name = models.CharField(max_length=120)
    block_number = models.CharField(max_length=60, blank=True, null=True)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=60, db_index=True)  # Italian Marble / Granite / ...

    # Real uploaded photo (fixes both the photo-update bug and the
    # slow-loading problem — see the "image_display_url" note below).
    image = models.ImageField(upload_to=slab_image_upload_to, blank=True, null=True)
    # External fallback URL (used by seed data, or when staff paste a link
    # instead of uploading a file). Only used when `image` isn't set.
    image_url = models.TextField(blank=True, null=True)

    length = models.FloatField()
    width = models.FloatField()
    unit = models.CharField(max_length=20, default="feet")  # meters|centimeters|feet|inches
    pieces = models.IntegerField(default=1)
    total_sq_ft = models.FloatField(default=0)
    total_sq_meters = models.FloatField(default=0)
    thickness_mm = models.FloatField(blank=True, null=True)
    finish = models.CharField(max_length=40, blank=True, null=True)  # Polished/Honed/Leathered/Flamed/Lappato
    price_per_sq_ft = models.FloatField(default=0)
    is_sold = models.BooleanField(default=False, db_index=True)
    lot_name = models.CharField(max_length=120, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "slabs"
        ordering = ["-created_at"]

    # ---------------------------------------------------------------
    # Why this exists: the old Flask version stored every slab photo as a
    # base64 data: URL directly in the `imageUrl` column, so every single
    # /api/slabs list call shipped the full-size (or client-compressed)
    # image bytes for every slab inline in the JSON body. That's what made
    # the catalog grid, the admin table and the enquiry cart all feel slow,
    # especially on mobile data. `image` is now a real Django ImageField:
    # the file lives on disk/MEDIA storage and the API just returns a
    # lightweight URL the browser can cache and lazy-load, exactly like any
    # other <img src>. Re-uploading a photo (see views.update_slab) also
    # replaces the file cleanly, instead of relying on a giant string being
    # correctly round-tripped through the JSON body on every edit.
    # ---------------------------------------------------------------
    def image_display_url(self, request=None):
        if self.image:
            url = self.image.url
            return request.build_absolute_uri(url) if request else url
        return self.image_url or None

    def to_dict(self, request=None):
        return {
            "id": self.id,
            "godownId": self.godown_id,
            "godownName": self.godown_name,
            "blockNumber": self.block_number,
            "title": self.title,
            "category": self.category,
            "imageUrl": self.image_display_url(request),
            "length": self.length,
            "width": self.width,
            "unit": self.unit,
            "pieces": self.pieces,
            "totalSqFt": self.total_sq_ft,
            "totalSqMeters": self.total_sq_meters,
            "thicknessMm": self.thickness_mm,
            "finish": self.finish,
            "pricePerSqFt": self.price_per_sq_ft,
            "isSold": self.is_sold,
            "lotName": self.lot_name,
            "createdAt": iso_z(self.created_at),
        }


class TrashItem(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=gen_id, editable=False)
    slab_snapshot = models.JSONField()
    deleted_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.CharField(max_length=80, blank=True, null=True)
    expires_at = models.DateTimeField(default=make_trash_expiry)

    class Meta:
        db_table = "trash_items"
        ordering = ["-deleted_at"]

    def to_dict(self):
        remaining = None
        if self.expires_at:
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            remaining = max(0, (exp - utcnow()).days)
        return {
            "id": self.id,
            "slab": self.slab_snapshot,
            "deletedAt": iso_z(self.deleted_at),
            "deletedBy": self.deleted_by,
            "expiresAt": iso_z(self.expires_at),
            "remainingDays": remaining,
        }


class CustomerQuery(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=gen_id, editable=False)
    order_number = models.CharField(max_length=40, blank=True, null=True)
    client_name = models.CharField(max_length=120)
    mobile_number = models.CharField(max_length=30)
    delivery_address = models.TextField(blank=True, null=True)
    preferred_godown = models.CharField(max_length=32, default="any")
    requirement = models.TextField(blank=True, null=True)
    dimension_unit = models.CharField(max_length=20, default="feet")
    requested_quantity_sqft = models.FloatField(default=0)
    selected_slabs = models.JSONField(default=list)
    total_estimated_cost = models.FloatField(blank=True, null=True)
    status = models.CharField(max_length=20, default="Pending")  # Pending/Contacted/Quoted/Closed
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "customer_queries"
        ordering = ["-created_at"]

    def to_dict(self):
        return {
            "id": self.id,
            "orderNumber": self.order_number,
            "clientName": self.client_name,
            "mobileNumber": self.mobile_number,
            "deliveryAddress": self.delivery_address,
            "preferredGodown": self.preferred_godown,
            "requirement": self.requirement,
            "dimensionUnit": self.dimension_unit,
            "requestedQuantitySqFt": self.requested_quantity_sqft,
            "selectedSlabs": self.selected_slabs or [],
            "totalEstimatedCost": self.total_estimated_cost,
            "status": self.status,
            "createdAt": iso_z(self.created_at),
            "notes": self.notes,
        }


class Announcement(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=gen_id, editable=False)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    type = models.CharField(max_length=20, default="general")  # offer/arrival/general
    date = models.CharField(max_length=40, blank=True, null=True)

    class Meta:
        db_table = "announcements"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "isActive": self.is_active,
            "type": self.type,
            "date": self.date,
        }
