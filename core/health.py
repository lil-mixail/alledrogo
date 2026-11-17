from django.http import HttpResponse


class HealthCheckMiddleware:
    # health check z ALB idzie po HTTP na prywatne IP serwera,
    # wiec odpowiadamy zanim Django sprawdzi ALLOWED_HOSTS i przekieruje na https
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
