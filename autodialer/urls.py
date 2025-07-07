from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    re_path(r'^admin/(?P<app_label>auth|core|users)/$', admin.site.app_index, name='app_list'),
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('users/', include('users.urls')),
    path('campaigns/', include('campaigns.urls')),
#    path('leads/', include('leads.urls')),
#    path('telephony/', include('telephony.urls')),
#    path('agents/', include('agents.urls')),
#    path('calls/', include('calls.urls')),
#    path('reports/', include('reports.urls')),
#    path('settings/', include('settings.urls')),
    path('dashboard/', include('core.urls', namespace='dashboard')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
