import uuid
from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

TRASH_RETENTION_DAYS = 7


def gen_id():
    return uuid.uuid4().hex


class Slab(db.Model):
    __tablename__ = "slabs"

    id = db.Column(db.String(36), primary_key=True, default=gen_id)
    godown_id = db.Column(db.String(32), nullable=False)          # godown_1 / godown_2 / godown_3
    godown_name = db.Column(db.String(120), nullable=False)
    block_number = db.Column(db.String(60))
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(60), nullable=False)           # Italian Marble / Granite / ...
    image_url = db.Column(db.Text)
    length = db.Column(db.Float, nullable=False)
    width = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default="feet")  # meters|centimeters|feet|inches
    pieces = db.Column(db.Integer, nullable=False, default=1)
    total_sq_ft = db.Column(db.Float, nullable=False, default=0)
    total_sq_meters = db.Column(db.Float, nullable=False, default=0)
    thickness_mm = db.Column(db.Float)
    finish = db.Column(db.String(40))                              # Polished/Honed/Leathered/Flamed/Lappato
    price_per_sq_ft = db.Column(db.Float, nullable=False, default=0)
    is_sold = db.Column(db.Boolean, nullable=False, default=False)
    lot_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "godownId": self.godown_id,
            "godownName": self.godown_name,
            "blockNumber": self.block_number,
            "title": self.title,
            "category": self.category,
            "imageUrl": self.image_url,
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
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class TrashItem(db.Model):
    __tablename__ = "trash_items"

    id = db.Column(db.String(36), primary_key=True, default=gen_id)
    slab_snapshot = db.Column(db.JSON, nullable=False)
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_by = db.Column(db.String(80))
    expires_at = db.Column(db.DateTime)

    def to_dict(self):
        remaining = None
        if self.expires_at:
            remaining = max(0, (self.expires_at - datetime.utcnow()).days)
        return {
            "id": self.id,
            "slab": self.slab_snapshot,
            "deletedAt": self.deleted_at.isoformat() + "Z" if self.deleted_at else None,
            "deletedBy": self.deleted_by,
            "expiresAt": self.expires_at.isoformat() + "Z" if self.expires_at else None,
            "remainingDays": remaining,
        }


class CustomerQuery(db.Model):
    __tablename__ = "customer_queries"

    id = db.Column(db.String(36), primary_key=True, default=gen_id)
    order_number = db.Column(db.String(40))
    client_name = db.Column(db.String(120), nullable=False)
    mobile_number = db.Column(db.String(30), nullable=False)
    delivery_address = db.Column(db.Text)
    preferred_godown = db.Column(db.String(32), default="any")
    requirement = db.Column(db.Text)
    dimension_unit = db.Column(db.String(20), default="feet")
    requested_quantity_sqft = db.Column(db.Float, default=0)
    selected_slabs = db.Column(db.JSON, default=list)
    total_estimated_cost = db.Column(db.Float)
    status = db.Column(db.String(20), default="Pending")  # Pending/Contacted/Quoted/Closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

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
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
            "notes": self.notes,
        }


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.String(36), primary_key=True, default=gen_id)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(20), default="general")  # offer/arrival/general
    date = db.Column(db.String(40))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "isActive": self.is_active,
            "type": self.type,
            "date": self.date,
        }


def make_trash_expiry():
    return datetime.utcnow() + timedelta(days=TRASH_RETENTION_DAYS)
