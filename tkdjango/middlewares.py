# tkdjango/middlewares.py
from django.http import HttpResponse
from django.conf import settings
from urllib.parse import urlencode
from django.http import HttpResponseRedirect

def _origin():
    # همون FRONTEND_URL که در settings گذاشتی
    return getattr(settings, "FRONTEND_URL", "https://chbtkd.ir")

class PreflightMiddleware:
    """
    تمام OPTIONS های مسیرهای /api/ را short-circuit می‌کند
    تا CORS preflight بدون درگیری سایر middleware/CSRF/DRF با 204 برگردد.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            resp = HttpResponse(status=204)
            resp["Access-Control-Allow-Origin"] = _origin()
            resp["Access-Control-Allow-Credentials"] = "true"
            resp["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRFToken, X-Role-Group"
            resp["Vary"] = "Origin"
            return resp
        return self.get_response(request)

class StripCsrfFromGatewayQueryMiddleware:
    """
    اگر کسی/چیزی csrfmiddlewaretoken را به URL مسیر go-to-bank-gateway اضافه کرد،
    آن را حذف می‌کنیم تا loop نشود.
    """
    GATEWAY_PATH = "/bankgateways/go-to-bank-gateway/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and request.path.startswith(self.GATEWAY_PATH):

            if "csrfmiddlewaretoken" in request.GET:
                # فقط پارامترهای لازم را نگه دار (tc)
                tc = request.GET.get("tc") or request.GET.get("tracking_code")
                params = {}
                if tc:
                    params["tc"] = tc

                new_qs = urlencode(params) if params else ""
                clean_url = self.GATEWAY_PATH + (f"?{new_qs}" if new_qs else "")
                return HttpResponseRedirect(clean_url)

        return self.get_response(request) 
