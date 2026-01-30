# tkdjango/gateway_override.py
from urllib.parse import urlencode
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

# تلاش برای import سازگار با نسخه‌های مختلف
try:
    from azbankgateways.views import go_to_bank_gateway as _go_to_bank_gateway
except Exception:
    from azbankgateways import views as _gw_views
    _go_to_bank_gateway = getattr(_gw_views, "go_to_bank_gateway")

@csrf_exempt
def go_to_bank_gateway(request, *args, **kwargs):
    """
    1) اگر csrfmiddlewaretoken در query بود، حذفش کن و فقط tc را نگه دار
    2) سپس view اصلی پکیج را اجرا کن
    """
    if request.method == "GET" and "csrfmiddlewaretoken" in request.GET:
        tc = request.GET.get("tc") or request.GET.get("tracking_code")
        params = {}
        if tc:
            params["tc"] = tc
        qs = urlencode(params) if params else ""
        clean_url = request.path + (f"?{qs}" if qs else "")
        return HttpResponseRedirect(clean_url)

    return _go_to_bank_gateway(request, *args, **kwargs)
