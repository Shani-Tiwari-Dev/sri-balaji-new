import csv
import io
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from config import Config
from models import db, Slab, TrashItem, CustomerQuery, Announcement, make_trash_expiry
from utils.calc import calculate_slab_area, get_rates_in_all_units, format_currency_inr
from utils.auth import (
    resolve_role, issue_token, require_staff, godown_scope_ok, GODOWNS,
)

FRONTEND_DIR = "../frontend"


def create_app():
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.config.from_object(Config)
    CORS(app, origins=app.config["CORS_ORIGINS"])
    db.init_app(app)

    # Create tables on startup. This runs the first time the app/module is
    # loaded (works for `python app.py`, gunicorn, AND serverless platforms
    # like Vercel where there's no separate "first run" step). Safe to call
    # repeatedly — create_all() only creates tables that don't exist yet.
    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:  # pragma: no cover - don't crash cold start on a transient DB hiccup
            app.logger.warning("db.create_all() failed at startup: %s", exc)

    # Without this, an unhandled exception returns Flask's default HTML
    # error page. The frontend's fetch wrapper expects JSON and falls back
    # to a generic "Request failed (500)" with no detail. This returns the
    # real error message instead, so it's actually debuggable from the
    # browser's Network tab (and from Vercel's function logs either way).
    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        app.logger.exception("Unhandled error")
        code = getattr(err, "code", 500)
        if not isinstance(code, int):
            code = 500
        if code == 413:
            return jsonify({"error": "That image is too large even after compression. Please try a smaller photo."}), 413
        return jsonify({"error": str(err) or err.__class__.__name__}), code

    # ---------------------------------------------------------------
    # Static frontend
    # ---------------------------------------------------------------
    @app.route("/")
    def serve_index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/staff")
    @app.route("/admin")
    def serve_staff():
        return send_from_directory(app.static_folder, "staff.html")

    @app.route("/<path:path>")
    def serve_static(path):
        return send_from_directory(app.static_folder, path)

    # ---------------------------------------------------------------
    # Public reference data
    # ---------------------------------------------------------------
    @app.get("/api/godowns")
    def get_godowns():
        return jsonify([{"id": k, "name": v} for k, v in GODOWNS.items()])

    @app.get("/api/meta")
    def get_meta():
        return jsonify({
            "categories": ["Italian Marble", "Indian Marble", "Granite", "Quartz", "Onyx", "Sandstone"],
            "finishes": ["Polished", "Honed", "Leathered", "Flamed", "Lappato"],
            "units": ["feet", "meters", "centimeters", "inches"],
            "whatsappNumber": app.config["WHATSAPP_NUMBER"],
            "whatsappNumberSecondary": app.config["WHATSAPP_NUMBER_SECONDARY"],
            "company": {
                "name": "Sri Balaji Granites & Marbles",
                "tagline": "We Have Granite & Marble, Black Stone, Wall Tiles, Floor Tiles & Marble Sinks Available",
                "primaryContact": "+91 98284 00811",
                "secondaryContact": "+91 99827 49180",
                "yardAddress": "Site No. 17, 18 & 19, Sir M. Vishveshwaraiah Extension, Southern side of CSI Hospital, Bengaluru Rural District – 562114",
                "factoryAddress": "Sri Balaji Granites & Factory, Chittoor",
                "exportCounter": "Suguna Export, Vishakapatnam",
            },
        })

    # ---------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------
    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400
        if password not in app.config["STAFF_PASSWORDS"]:
            return jsonify({"error": "Incorrect password."}), 401
        role = resolve_role(username)
        token, payload = issue_token(username, role)
        return jsonify({"token": token, "session": payload})

    # ---------------------------------------------------------------
    # Slabs — public read, staff write
    # ---------------------------------------------------------------
    def _slab_area_and_price(payload):
        area = calculate_slab_area(payload["length"], payload["width"], payload.get("unit", "feet"), payload.get("pieces", 1))
        return area

    @app.get("/api/slabs")
    def list_slabs():
        q = Slab.query
        category = request.args.get("category")
        godown = request.args.get("godown")
        search = request.args.get("search")
        in_stock_only = request.args.get("inStockOnly")

        if category and category.lower() != "all":
            q = q.filter(Slab.category == category)
        if godown and godown.lower() != "all":
            q = q.filter(Slab.godown_id == godown)
        if in_stock_only in ("true", "1", "yes"):
            q = q.filter(Slab.is_sold.is_(False))
        if search:
            like = f"%{search}%"
            q = q.filter(db.or_(Slab.title.ilike(like), Slab.block_number.ilike(like), Slab.lot_name.ilike(like)))

        slabs = q.order_by(Slab.created_at.desc()).all()
        return jsonify([s.to_dict(list_view=True) for s in slabs])

    @app.get("/api/slabs/<slab_id>")
    def get_slab(slab_id):
        slab = Slab.query.get(slab_id)
        if not slab:
            return jsonify({"error": "Slab not found."}), 404
        data = slab.to_dict()
        data["rates"] = get_rates_in_all_units(slab.price_per_sq_ft)
        data["estimatedValue"] = slab.total_sq_ft * slab.price_per_sq_ft
        data["estimatedValueFormatted"] = format_currency_inr(data["estimatedValue"])
        return jsonify(data)

    @app.post("/api/slabs")
    @require_staff
    def create_slab():
        payload = request.get_json(silent=True) or {}
        required = ["title", "category", "godownId", "length", "width"]
        missing = [f for f in required if not payload.get(f)]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
        if not godown_scope_ok(request.staff, payload["godownId"]):
            return jsonify({"error": "You do not have access to this godown."}), 403

        area = _slab_area_and_price(payload)
        slab = Slab(
            godown_id=payload["godownId"],
            godown_name=GODOWNS.get(payload["godownId"], payload["godownId"]),
            block_number=payload.get("blockNumber"),
            title=payload["title"],
            category=payload["category"],
            image_url=payload.get("imageUrl"),
            length=payload["length"],
            width=payload["width"],
            unit=payload.get("unit", "feet"),
            pieces=payload.get("pieces", 1),
            total_sq_ft=area["totalSqFt"],
            total_sq_meters=area["totalSqMeters"],
            thickness_mm=payload.get("thicknessMm"),
            finish=payload.get("finish"),
            price_per_sq_ft=payload.get("pricePerSqFt", 0),
            is_sold=payload.get("isSold", False),
            lot_name=payload.get("lotName"),
            thumbnail_url=payload.get("thumbnailUrl") or payload.get("imageUrl"),
        )
        db.session.add(slab)
        db.session.commit()
        return jsonify(slab.to_dict()), 201

    @app.put("/api/slabs/<slab_id>")
    @require_staff
    def update_slab(slab_id):
        slab = Slab.query.get(slab_id)
        if not slab:
            return jsonify({"error": "Slab not found."}), 404
        if not godown_scope_ok(request.staff, slab.godown_id):
            return jsonify({"error": "You do not have access to this godown."}), 403

        payload = request.get_json(silent=True) or {}
        for field, attr in [
            ("title", "title"), ("category", "category"), ("imageUrl", "image_url"),
            ("thumbnailUrl", "thumbnail_url"),
            ("blockNumber", "block_number"), ("length", "length"), ("width", "width"),
            ("unit", "unit"), ("pieces", "pieces"), ("thicknessMm", "thickness_mm"),
            ("finish", "finish"), ("pricePerSqFt", "price_per_sq_ft"),
            ("isSold", "is_sold"), ("lotName", "lot_name"),
        ]:
            if field in payload:
                setattr(slab, attr, payload[field])
        # Keep the list thumbnail in sync if a new full image was set without
        # an explicit thumbnail (e.g. someone pastes a plain image URL).
        if "imageUrl" in payload and "thumbnailUrl" not in payload:
            slab.thumbnail_url = payload["imageUrl"]

        if any(k in payload for k in ("length", "width", "unit", "pieces")):
            area = calculate_slab_area(slab.length, slab.width, slab.unit, slab.pieces)
            slab.total_sq_ft = area["totalSqFt"]
            slab.total_sq_meters = area["totalSqMeters"]

        if "godownId" in payload and godown_scope_ok(request.staff, payload["godownId"]):
            slab.godown_id = payload["godownId"]
            slab.godown_name = GODOWNS.get(payload["godownId"], payload["godownId"])

        db.session.commit()
        return jsonify(slab.to_dict())

    @app.delete("/api/slabs/<slab_id>")
    @require_staff
    def delete_slab(slab_id):
        """Soft-delete: move the slab into Trash rather than removing it."""
        slab = Slab.query.get(slab_id)
        if not slab:
            return jsonify({"error": "Slab not found."}), 404
        if not godown_scope_ok(request.staff, slab.godown_id):
            return jsonify({"error": "You do not have access to this godown."}), 403

        trash = TrashItem(
            slab_snapshot=slab.to_dict(),
            deleted_by=request.staff["username"],
            expires_at=make_trash_expiry(),
        )
        db.session.add(trash)
        db.session.delete(slab)
        db.session.commit()
        return jsonify(trash.to_dict()), 200

    # ---------------------------------------------------------------
    # Trash
    # ---------------------------------------------------------------
    def _purge_expired_trash():
        expired = TrashItem.query.filter(TrashItem.expires_at <= datetime.utcnow()).all()
        for item in expired:
            db.session.delete(item)
        if expired:
            db.session.commit()

    @app.get("/api/trash")
    @require_staff
    def list_trash():
        _purge_expired_trash()
        q = TrashItem.query
        items = q.order_by(TrashItem.deleted_at.desc()).all()
        if request.staff["role"] != "admin":
            gid = request.staff.get("godownId")
            items = [i for i in items if (i.slab_snapshot or {}).get("godownId") == gid]
        return jsonify([i.to_dict() for i in items])

    @app.post("/api/trash/<trash_id>/restore")
    @require_staff
    def restore_trash(trash_id):
        item = TrashItem.query.get(trash_id)
        if not item:
            return jsonify({"error": "Trash item not found."}), 404
        snap = item.slab_snapshot
        if not godown_scope_ok(request.staff, snap.get("godownId")):
            return jsonify({"error": "You do not have access to this godown."}), 403

        slab = Slab(
            id=snap.get("id"),
            godown_id=snap.get("godownId"),
            godown_name=snap.get("godownName"),
            block_number=snap.get("blockNumber"),
            title=snap.get("title"),
            category=snap.get("category"),
            image_url=snap.get("imageUrl"),
            length=snap.get("length"),
            width=snap.get("width"),
            unit=snap.get("unit", "feet"),
            pieces=snap.get("pieces", 1),
            total_sq_ft=snap.get("totalSqFt", 0),
            total_sq_meters=snap.get("totalSqMeters", 0),
            thickness_mm=snap.get("thicknessMm"),
            finish=snap.get("finish"),
            price_per_sq_ft=snap.get("pricePerSqFt", 0),
            is_sold=snap.get("isSold", False),
            lot_name=snap.get("lotName"),
        )
        # Avoid primary key clashes if the id already exists (rare)
        if Slab.query.get(slab.id):
            slab.id = None
        db.session.add(slab)
        db.session.delete(item)
        db.session.commit()
        return jsonify(slab.to_dict())

    @app.delete("/api/trash/<trash_id>")
    @require_staff
    def purge_trash_item(trash_id):
        item = TrashItem.query.get(trash_id)
        if not item:
            return jsonify({"error": "Trash item not found."}), 404
        if not godown_scope_ok(request.staff, (item.slab_snapshot or {}).get("godownId")):
            return jsonify({"error": "You do not have access to this godown."}), 403
        db.session.delete(item)
        db.session.commit()
        return jsonify({"deleted": True})

    # ---------------------------------------------------------------
    # Customer queries / enquiries
    # ---------------------------------------------------------------
    @app.post("/api/queries")
    def create_query():
        payload = request.get_json(silent=True) or {}
        if not payload.get("clientName") or not payload.get("mobileNumber"):
            return jsonify({"error": "Name and mobile number are required."}), 400

        order_number = "SBG-" + datetime.utcnow().strftime("%y%m%d") + "-" + str(
            (CustomerQuery.query.count() + 1)
        ).zfill(4)

        selected = payload.get("selectedSlabs", [])
        total_cost = sum((s.get("totalSqFt", 0) * s.get("pricePerSqFt", 0)) for s in selected) or payload.get("totalEstimatedCost")

        query = CustomerQuery(
            order_number=order_number,
            client_name=payload["clientName"],
            mobile_number=payload["mobileNumber"],
            delivery_address=payload.get("deliveryAddress"),
            preferred_godown=payload.get("preferredGodown", "any"),
            requirement=payload.get("requirement"),
            dimension_unit=payload.get("dimensionUnit", "feet"),
            requested_quantity_sqft=payload.get("requestedQuantitySqFt", 0),
            selected_slabs=selected,
            total_estimated_cost=total_cost,
            status="Pending",
        )
        db.session.add(query)
        db.session.commit()
        return jsonify(query.to_dict()), 201

    @app.get("/api/queries")
    @require_staff
    def list_queries():
        items = CustomerQuery.query.order_by(CustomerQuery.created_at.desc()).all()
        if request.staff["role"] != "admin":
            gid = request.staff.get("godownId")
            items = [i for i in items if i.preferred_godown in (gid, "any")]
        return jsonify([i.to_dict() for i in items])

    @app.put("/api/queries/<query_id>")
    @require_staff
    def update_query(query_id):
        item = CustomerQuery.query.get(query_id)
        if not item:
            return jsonify({"error": "Enquiry not found."}), 404
        payload = request.get_json(silent=True) or {}
        if "status" in payload:
            if payload["status"] not in ("Pending", "Contacted", "Quoted", "Closed"):
                return jsonify({"error": "Invalid status."}), 400
            item.status = payload["status"]
        if "notes" in payload:
            item.notes = payload["notes"]
        db.session.commit()
        return jsonify(item.to_dict())

    # ---------------------------------------------------------------
    # Announcements
    # ---------------------------------------------------------------
    @app.get("/api/announcements")
    def list_active_announcements():
        items = Announcement.query.filter_by(is_active=True).all()
        return jsonify([a.to_dict() for a in items])

    @app.get("/api/announcements/all")
    @require_staff
    def list_all_announcements():
        items = Announcement.query.order_by(Announcement.date.desc()).all()
        return jsonify([a.to_dict() for a in items])

    @app.post("/api/announcements")
    @require_staff
    def create_announcement():
        payload = request.get_json(silent=True) or {}
        if not payload.get("title") or not payload.get("message"):
            return jsonify({"error": "Title and message are required."}), 400
        item = Announcement(
            title=payload["title"],
            message=payload["message"],
            type=payload.get("type", "general"),
            is_active=payload.get("isActive", True),
            date=datetime.utcnow().strftime("%Y-%m-%d"),
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201

    @app.put("/api/announcements/<ann_id>")
    @require_staff
    def update_announcement(ann_id):
        item = Announcement.query.get(ann_id)
        if not item:
            return jsonify({"error": "Announcement not found."}), 404
        payload = request.get_json(silent=True) or {}
        for field, attr in [("title", "title"), ("message", "message"), ("type", "type"), ("isActive", "is_active")]:
            if field in payload:
                setattr(item, attr, payload[field])
        db.session.commit()
        return jsonify(item.to_dict())

    @app.delete("/api/announcements/<ann_id>")
    @require_staff
    def delete_announcement(ann_id):
        item = Announcement.query.get(ann_id)
        if not item:
            return jsonify({"error": "Announcement not found."}), 404
        db.session.delete(item)
        db.session.commit()
        return jsonify({"deleted": True})

    # ---------------------------------------------------------------
    # Reports
    # ---------------------------------------------------------------
    @app.get("/api/reports/summary")
    @require_staff
    def reports_summary():
        q = Slab.query
        if request.staff["role"] != "admin":
            q = q.filter(Slab.godown_id == request.staff.get("godownId"))
        slabs = q.all()
        in_stock = [s for s in slabs if not s.is_sold]
        sold = [s for s in slabs if s.is_sold]
        total_value = sum(s.total_sq_ft * s.price_per_sq_ft for s in in_stock)
        by_category = {}
        for s in in_stock:
            by_category.setdefault(s.category, {"count": 0, "sqft": 0, "value": 0})
            by_category[s.category]["count"] += 1
            by_category[s.category]["sqft"] += s.total_sq_ft
            by_category[s.category]["value"] += s.total_sq_ft * s.price_per_sq_ft
        return jsonify({
            "totalSlabs": len(slabs),
            "inStockCount": len(in_stock),
            "soldCount": len(sold),
            "totalStockValue": round(total_value, 2),
            "totalStockValueFormatted": format_currency_inr(total_value),
            "byCategory": by_category,
        })

    @app.get("/api/reports/export.csv")
    @require_staff
    def export_csv():
        q = Slab.query
        if request.staff["role"] != "admin":
            q = q.filter(Slab.godown_id == request.staff.get("godownId"))
        slabs = q.all()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Godown", "Block #", "Title", "Category", "Length", "Width", "Unit", "Pieces",
                          "Total Sq.Ft", "Total Sq.M", "Thickness", "Finish", "Rate", "Estimated Value", "Status"])
        for s in slabs:
            writer.writerow([
                s.godown_name, s.block_number, s.title, s.category, s.length, s.width, s.unit, s.pieces,
                s.total_sq_ft, s.total_sq_meters, s.thickness_mm, s.finish, s.price_per_sq_ft,
                round(s.total_sq_ft * s.price_per_sq_ft, 2), "Sold" if s.is_sold else "In Stock",
            ])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=stock_export.csv"},
        )

    # ---------------------------------------------------------------
    # Calculator (used by the staff Calculator tab for quick conversions)
    # ---------------------------------------------------------------
    @app.post("/api/calc/area")
    def calc_area():
        payload = request.get_json(silent=True) or {}
        try:
            area = calculate_slab_area(payload["length"], payload["width"], payload.get("unit", "feet"), payload.get("pieces", 1))
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "length and width are required numbers."}), 400
        rate = payload.get("pricePerSqFt")
        result = {"area": area}
        if rate is not None:
            result["rates"] = get_rates_in_all_units(rate)
            result["estimatedValue"] = area["totalSqFt"] * float(rate)
            result["estimatedValueFormatted"] = format_currency_inr(result["estimatedValue"])
        return jsonify(result)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=app.config.get("FLASK_DEBUG", True))
