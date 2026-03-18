from django.http import JsonResponse
from django.db import connections
from django.core.cache import cache

def healthz(request):
    return JsonResponse({"status": "ok"}, status=200)

def readyz(request):
    try:
        connections["default"].cursor().execute("SELECT 1;")
    except Exception:
        return JsonResponse({"status": "db_down"}, status=503)

    try:
        cache.set("readyz_probe", "1", timeout=5)
        if cache.get("readyz_probe") != "1":
            raise RuntimeError("cache_mismatch")
    except Exception:
        return JsonResponse({"status": "cache_down"}, status=503)

    return JsonResponse({"status": "ready"}, status=200)