from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Alledrogo – panel administracyjny"
admin.site.site_title = "Alledrogo admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("konto/", include("accounts.urls")),
    path("produkty/", include("products.urls")),
    path("zamowienia/", include("orders.urls")),
    path("", include("core.urls")),
]

handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
