"""vristo URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from .views import contact_us, index, subscribe_newsletter, track_shipment


handler404 = "idiotship.views.custom_404"
handler500 = "idiotship.views.custom_500"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),
    path("track-shipment/", track_shipment, name="track-shipment"),
    path("subscribe_newsletter/", subscribe_newsletter, name="subscribe-newsletter"),
    path("contact_us/", contact_us, name="contact-us"),
    # panel urls
    path("user_panel/", include("user_panel.urls")),
    path("admin_panel/", include("admin_panel.urls")),
    path("superadmin_panel/", include("superadmin_panel.urls")),
    # user urls
    path("account/", include("account.urls")),
    path("wallet/", include("wallet.urls")),
    path("order/", include("order_manager.urls")),
    # shopify 
    path("shopify/", include("shopify_integration.urls")),
    # webhooks
    path("xpressbees-integration/", include("xpressbees_integration.urls")),
    path("lastmiles-integration/", include("lastmiles_integration.urls")),
    path("purple-drone-integration/", include("purple_drone_integration.urls")),
    path("parcelx-integration/", include("parcelx_integration.urls")),
    path("sr-integration/", include("shiprocket_integration.urls")),
    path("jiffy-integration/", include("jiffy_integration.urls")),
    path("fship-integration/", include("fship_integration.urls")),
    path("rapidshyp-integration/", include("rapidshyp_integration.urls")),
    path("rapidshyp-new-integration/", include("rapidshyp_new_integration.urls")),
    path("nimbuspost-integration/", include("nimbuspost_integration.urls")),
    path("smartship-integration/", include("smartship_integration.urls")),
    path("bdl-integration/", include("bdl_integration.urls")),
    path("zippyy-integration/", include("zippyy_integration.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [path("sentry-debug/", lambda request: 1 / 0)]
