import datetime
from functools import wraps

import jwt
from django.conf import settings
from django.http import JsonResponse

GODOWNS = {
    "godown_1": "Bangalore Yard",
    "godown_2": "Chittoor Factory",
    "godown_3": "Vishakapatnam Export",
}

ROLE_USERNAME_MAP = {
    "manager_godown_1": ["manager_godown_1", "manager_g1", "manager_a", "bangalore", "g1"],
    "manager_godown_2": ["manager_godown_2", "manager_g2", "manager_b", "chittoor", "g2"],
    "manager_godown_3": ["manager_godown_3", "manager_g3", "manager_c", "vizag", "vishakapatnam", "g3"],
    "admin": ["admin", "shayam", "shayam_admin", "superadmin"],
}

ROLE_GODOWN = {
    "manager_godown_1": "godown_1",
    "manager_godown_2": "godown_2",
    "manager_godown_3": "godown_3",
}


def resolve_role(username: str) -> str:
    uname = (username or "").strip().lower()
    for role, triggers in ROLE_USERNAME_MAP.items():
        if uname in triggers:
            return role
    # Any unrecognized username falls back to Super Admin, matching the
    # original prototype's behaviour (documented in the project report).
    return "admin"


def issue_token(username: str, role: str):
    godown_id = ROLE_GODOWN.get(role)
    payload = {
        "username": username,
        "name": username,
        "role": role,
        "godownId": godown_id,
        "godownName": GODOWNS.get(godown_id) if godown_id else None,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, payload


def decode_token(token: str):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def require_staff(view_func):
    """Decorator: requires a valid staff bearer token. Attaches request.staff."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JsonResponse({"error": "Staff login required."}, status=401)
        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Session expired. Please log in again."}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({"error": "Invalid session token."}, status=401)
        request.staff = payload
        return view_func(request, *args, **kwargs)
    return wrapper


def godown_scope_ok(staff_payload, godown_id) -> bool:
    """True if this staff member is allowed to act on the given godown."""
    if staff_payload["role"] == "admin":
        return True
    return staff_payload.get("godownId") == godown_id
