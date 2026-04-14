from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.views.generic import TemplateView

from leagues.views import home

urlpatterns = [
    path('health/', lambda r: HttpResponse('ok')),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', home, name='home'),
    path('', include('leagues.urls')),
    path('', include('matches.urls')),
]
