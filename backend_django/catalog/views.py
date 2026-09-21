import csv
import io
import json
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .auth import GODOWNS, godown_scope_ok, issue_token, require_staff, resolve_role
from .calc import calculate_slab_area, format_currency_inr, get_rates_in_all_units
from .models import Announcement, CustomerQuery, Slab, TrashItem, gen_id, make_trash_expiry


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def _is_multipart(request):
    return request.content_type and request.content_type.startswith("multipart/form-data")


def _slab_payload(request):
    """Read a slab create/update payload from either JSON or multipart form
    data (multipart is used when staff actually attach a photo file)."""
    if _is_multipart(request):
        payload = {k: v for k, v in request.POST.items()}
        for bool_field in ("isSold",):
            if bool_field in payload:
                payload[bool_field] = payload[bool_field] in ("true", "1", "True", "on")
        return payload, request.FILES.get("image")
    return _json_body(request), None


# ---------------------------------------------------------------------
# Public reference data
# ---------------------------------------------------------------------
def get_godowns(request):
    return JsonResponse([{"id": k, "name": v} for k, v in GODOWNS.items()], safe=False)


def get_meta(request):
    return JsonResponse({
        "categories": ["Italian Marble", "Indian Marble", "Granite", "Quartz", "Onyx", "Sandstone"],
        "finishes": ["Polished", "Honed", "Leathered", "Flamed", "Lappato"],
        "units": ["feet", "meters", "centimeters", "inches"],
        "whatsappNumber": settings.WHATSAPP_NUMBER,
        "whatsappNumberSecondary": settings.WHATSAPP_NUMBER_SECONDARY,
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


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    data = _json_body(request)
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return JsonResponse({"error": "Username and password are required."}, status=400)
    if password not in settings.STAFF_PASSWORDS:
        return JsonResponse({"error": "Incorrect password."}, status=401)
    role = resolve_role(username)
    token, payload = issue_token(username, role)
    return JsonResponse({"token": token, "session": payload})


# ---------------------------------------------------------------------
# Slabs — public read, staff write
# ---------------------------------------------------------------------
@csrf_exempt
def slabs_collection(request):
    if request.method == "GET":
        return _list_slabs(request)
    if request.method == "POST":
        return _create_slab(request)
    return JsonResponse({"error": "Method not allowed."}, status=405)


def _list_slabs(request):
    qs = Slab.objects.all()
    category = request.GET.get("category")
    godown = request.GET.get("godown")
    search = request.GET.get("search")
    in_stock_only = request.GET.get("inStockOnly")

    if category and category.lower() != "all":
        qs = qs.filter(category=category)
    if godown and godown.lower() != "all":
        qs = qs.filter(godown_id=godown)
    if in_stock_only in ("true", "1", "yes"):
        qs = qs.filter(is_sold=False)
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(title__icontains=search) | Q(block_number__icontains=search) | Q(lot_name__icontains=search))

    slabs = qs.order_by("-created_at")
    return JsonResponse([s.to_dict(request) for s in slabs], safe=False)


@require_staff
def _create_slab(request):
    payload, image_file = _slab_payload(request)
    required = ["title", "category", "godownId", "length", "width"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return JsonResponse({"error": f"Missing fields: {', '.join(missing)}"}, status=400)
    if not godown_scope_ok(request.staff, payload["godownId"]):
        return JsonResponse({"error": "You do not have access to this godown."}, status=403)

    area = calculate_slab_area(payload["length"], payload["width"], payload.get("unit", "feet"), int(payload.get("pieces", 1) or 1))
    slab = Slab(
        godown_id=payload["godownId"],
        godown_name=GODOWNS.get(payload["godownId"], payload["godownId"]),
        block_number=payload.get("blockNumber") or None,
        title=payload["title"],
        category=payload["category"],
        length=payload["length"],
        width=payload["width"],
        unit=payload.get("unit", "feet"),
        pieces=int(payload.get("pieces", 1) or 1),
        total_sq_ft=area["totalSqFt"],
        total_sq_meters=area["totalSqMeters"],
        thickness_mm=payload.get("thicknessMm") or None,
        finish=payload.get("finish") or None,
        price_per_sq_ft=payload.get("pricePerSqFt", 0) or 0,
        is_sold=payload.get("isSold", False),
        lot_name=payload.get("lotName") or None,
    )
    if image_file:
        slab.image = image_file
    else:
        slab.image_url = payload.get("imageUrl") or None
    slab.save()
    return JsonResponse(slab.to_dict(request), status=201)


@csrf_exempt
def slab_detail(request, slab_id):
    if request.method == "GET":
        return _get_slab(request, slab_id)
    if request.method == "PUT":
        return _update_slab(request, slab_id)
    if request.method == "DELETE":
        return _delete_slab(request, slab_id)
    return JsonResponse({"error": "Method not allowed."}, status=405)


def _get_slab(request, slab_id):
    try:
        slab = Slab.objects.get(pk=slab_id)
    except Slab.DoesNotExist:
        return JsonResponse({"error": "Slab not found."}, status=404)
    data = slab.to_dict(request)
    data["rates"] = get_rates_in_all_units(slab.price_per_sq_ft)
    data["estimatedValue"] = slab.total_sq_ft * slab.price_per_sq_ft
    data["estimatedValueFormatted"] = format_currency_inr(data["estimatedValue"])
    return JsonResponse(data)


FIELD_MAP = [
    ("title", "title"), ("category", "category"),
    ("blockNumber", "block_number"), ("length", "length"), ("width", "width"),
    ("unit", "unit"), ("pieces", "pieces"), ("thicknessMm", "thickness_mm"),
    ("finish", "finish"), ("pricePerSqFt", "price_per_sq_ft"),
    ("isSold", "is_sold"), ("lotName", "lot_name"),
]


@require_staff
def _update_slab(request, slab_id):
    try:
        slab = Slab.objects.get(pk=slab_id)
    except Slab.DoesNotExist:
        return JsonResponse({"error": "Slab not found."}, status=404)
    if not godown_scope_ok(request.staff, slab.godown_id):
        return JsonResponse({"error": "You do not have access to this godown."}, status=403)

    NUMERIC_ATTRS = {"length", "width", "pieces", "thickness_mm", "price_per_sq_ft"}
    payload, image_file = _slab_payload(request)
    for field, attr in FIELD_MAP:
        if field not in payload:
            continue
        value = payload[field]
        if attr in NUMERIC_ATTRS and value in ("", None):
            continue  # blank numeric input from the form — leave the existing value alone
        if attr == "pieces":
            value = int(value)
        setattr(slab, attr, value)

    # Replacing the photo: this is the fix for the old "photo update"
    # problem — uploading a new file now cleanly replaces the stored file
    # (and deletes the old one) instead of relying on a base64 string being
    # correctly carried through the whole JSON round-trip.
    if image_file:
        if slab.image:
            slab.image.delete(save=False)
        slab.image = image_file
        slab.image_url = None
    elif "imageUrl" in payload and payload["imageUrl"]:
        slab.image_url = payload["imageUrl"]

    if any(k in payload for k in ("length", "width", "unit", "pieces")):
        area = calculate_slab_area(slab.length, slab.width, slab.unit, slab.pieces)
        slab.total_sq_ft = area["totalSqFt"]
        slab.total_sq_meters = area["totalSqMeters"]

    if payload.get("godownId") and godown_scope_ok(request.staff, payload["godownId"]):
        slab.godown_id = payload["godownId"]
        slab.godown_name = GODOWNS.get(payload["godownId"], payload["godownId"])

    slab.save()
    return JsonResponse(slab.to_dict(request))


@require_staff
def _delete_slab(request, slab_id):
    """Soft-delete: move the slab into Trash rather than removing it."""
    try:
        slab = Slab.objects.get(pk=slab_id)
    except Slab.DoesNotExist:
        return JsonResponse({"error": "Slab not found."}, status=404)
    if not godown_scope_ok(request.staff, slab.godown_id):
        return JsonResponse({"error": "You do not have access to this godown."}, status=403)

    trash = TrashItem.objects.create(
        slab_snapshot=slab.to_dict(request),
        deleted_by=request.staff["username"],
        expires_at=make_trash_expiry(),
    )
    slab.delete()
    return JsonResponse(trash.to_dict(), status=200)


# ---------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------
def _purge_expired_trash():
    from .models import utcnow
    TrashItem.objects.filter(expires_at__lte=utcnow()).delete()


@require_staff
def list_trash(request):
    _purge_expired_trash()
    items = TrashItem.objects.all().order_by("-deleted_at")
    if request.staff["role"] != "admin":
        gid = request.staff.get("godownId")
        items = [i for i in items if (i.slab_snapshot or {}).get("godownId") == gid]
    return JsonResponse([i.to_dict() for i in items], safe=False)


@csrf_exempt
@require_staff
@require_http_methods(["POST"])
def restore_trash(request, trash_id):
    try:
        item = TrashItem.objects.get(pk=trash_id)
    except TrashItem.DoesNotExist:
        return JsonResponse({"error": "Trash item not found."}, status=404)
    snap = item.slab_snapshot
    if not godown_scope_ok(request.staff, snap.get("godownId")):
        return JsonResponse({"error": "You do not have access to this godown."}, status=403)

    slab_id = snap.get("id")
    if slab_id and Slab.objects.filter(pk=slab_id).exists():
        slab_id = None  # avoid primary key clash if it already exists (rare)

    slab = Slab.objects.create(
        id=slab_id or gen_id(),
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
    item.delete()
    return JsonResponse(slab.to_dict(request))


@csrf_exempt
@require_staff
@require_http_methods(["DELETE"])
def purge_trash_item(request, trash_id):
    try:
        item = TrashItem.objects.get(pk=trash_id)
    except TrashItem.DoesNotExist:
        return JsonResponse({"error": "Trash item not found."}, status=404)
    if not godown_scope_ok(request.staff, (item.slab_snapshot or {}).get("godownId")):
        return JsonResponse({"error": "You do not have access to this godown."}, status=403)
    item.delete()
    return JsonResponse({"deleted": True})


# ---------------------------------------------------------------------
# Customer queries / enquiries
# ---------------------------------------------------------------------
@csrf_exempt
def queries_collection(request):
    if request.method == "POST":
        return _create_query(request)
    if request.method == "GET":
        return _list_queries(request)
    return JsonResponse({"error": "Method not allowed."}, status=405)


def _create_query(request):
    payload = _json_body(request)
    if not payload.get("clientName") or not payload.get("mobileNumber"):
        return JsonResponse({"error": "Name and mobile number are required."}, status=400)

    order_number = "SBG-" + datetime.utcnow().strftime("%y%m%d") + "-" + str(
        CustomerQuery.objects.count() + 1
    ).zfill(4)

    selected = payload.get("selectedSlabs", [])
    total_cost = sum((s.get("totalSqFt", 0) * s.get("pricePerSqFt", 0)) for s in selected) or payload.get("totalEstimatedCost")

    query = CustomerQuery.objects.create(
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
    return JsonResponse(query.to_dict(), status=201)


@require_staff
def _list_queries(request):
    items = CustomerQuery.objects.all().order_by("-created_at")
    if request.staff["role"] != "admin":
        gid = request.staff.get("godownId")
        items = [i for i in items if i.preferred_godown in (gid, "any")]
    return JsonResponse([i.to_dict() for i in items], safe=False)


@csrf_exempt
@require_staff
@require_http_methods(["PUT"])
def update_query(request, query_id):
    try:
        item = CustomerQuery.objects.get(pk=query_id)
    except CustomerQuery.DoesNotExist:
        return JsonResponse({"error": "Enquiry not found."}, status=404)
    payload = _json_body(request)
    if "status" in payload:
        if payload["status"] not in ("Pending", "Contacted", "Quoted", "Closed"):
            return JsonResponse({"error": "Invalid status."}, status=400)
        item.status = payload["status"]
    if "notes" in payload:
        item.notes = payload["notes"]
    item.save()
    return JsonResponse(item.to_dict())


# ---------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------
def list_active_announcements(request):
    items = Announcement.objects.filter(is_active=True)
    return JsonResponse([a.to_dict() for a in items], safe=False)


@require_staff
def list_all_announcements(request):
    items = Announcement.objects.all().order_by("-date")
    return JsonResponse([a.to_dict() for a in items], safe=False)


@csrf_exempt
def announcements_collection(request):
    if request.method == "GET":
        return list_active_announcements(request)
    if request.method == "POST":
        return _create_announcement(request)
    return JsonResponse({"error": "Method not allowed."}, status=405)


@require_staff
def _create_announcement(request):
    payload = _json_body(request)
    if not payload.get("title") or not payload.get("message"):
        return JsonResponse({"error": "Title and message are required."}, status=400)
    item = Announcement.objects.create(
        title=payload["title"],
        message=payload["message"],
        type=payload.get("type", "general"),
        is_active=payload.get("isActive", True),
        date=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    return JsonResponse(item.to_dict(), status=201)


@csrf_exempt
def announcement_detail(request, ann_id):
    if request.method == "PUT":
        return _update_announcement(request, ann_id)
    if request.method == "DELETE":
        return _delete_announcement(request, ann_id)
    return JsonResponse({"error": "Method not allowed."}, status=405)


@require_staff
def _update_announcement(request, ann_id):
    try:
        item = Announcement.objects.get(pk=ann_id)
    except Announcement.DoesNotExist:
        return JsonResponse({"error": "Announcement not found."}, status=404)
    payload = _json_body(request)
    for field, attr in [("title", "title"), ("message", "message"), ("type", "type"), ("isActive", "is_active")]:
        if field in payload:
            setattr(item, attr, payload[field])
    item.save()
    return JsonResponse(item.to_dict())


@require_staff
def _delete_announcement(request, ann_id):
    try:
        item = Announcement.objects.get(pk=ann_id)
    except Announcement.DoesNotExist:
        return JsonResponse({"error": "Announcement not found."}, status=404)
    item.delete()
    return JsonResponse({"deleted": True})


# ---------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------
@require_staff
def reports_summary(request):
    qs = Slab.objects.all()
    if request.staff["role"] != "admin":
        qs = qs.filter(godown_id=request.staff.get("godownId"))
    slabs = list(qs)
    in_stock = [s for s in slabs if not s.is_sold]
    sold = [s for s in slabs if s.is_sold]
    total_value = sum(s.total_sq_ft * s.price_per_sq_ft for s in in_stock)
    by_category = {}
    for s in in_stock:
        entry = by_category.setdefault(s.category, {"count": 0, "sqft": 0, "value": 0})
        entry["count"] += 1
        entry["sqft"] += s.total_sq_ft
        entry["value"] += s.total_sq_ft * s.price_per_sq_ft
    return JsonResponse({
        "totalSlabs": len(slabs),
        "inStockCount": len(in_stock),
        "soldCount": len(sold),
        "totalStockValue": round(total_value, 2),
        "totalStockValueFormatted": format_currency_inr(total_value),
        "byCategory": by_category,
    })


@require_staff
def export_csv(request):
    qs = Slab.objects.all()
    if request.staff["role"] != "admin":
        qs = qs.filter(godown_id=request.staff.get("godownId"))
    slabs = list(qs)

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
    response = HttpResponse(buf.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=stock_export.csv"
    return response


# ---------------------------------------------------------------------
# Calculator (used by the staff Calculator tab for quick conversions)
# ---------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["POST"])
def calc_area(request):
    payload = _json_body(request)
    try:
        area = calculate_slab_area(payload["length"], payload["width"], payload.get("unit", "feet"), payload.get("pieces", 1))
    except (KeyError, TypeError, ValueError):
        return JsonResponse({"error": "length and width are required numbers."}, status=400)
    rate = payload.get("pricePerSqFt")
    result = {"area": area}
    if rate is not None:
        result["rates"] = get_rates_in_all_units(rate)
        result["estimatedValue"] = area["totalSqFt"] * float(rate)
        result["estimatedValueFormatted"] = format_currency_inr(result["estimatedValue"])
    return JsonResponse(result)


def health(request):
    return JsonResponse({"status": "ok"})
