from django.urls import path

from . import views
from standings.views import StandingsView

app_name = 'leagues'

urlpatterns = [
    path('seasons/', views.SeasonListView.as_view(), name='season_list'),
    path('seasons/<int:pk>/', views.SeasonDetailView.as_view(), name='season_detail'),
    path('seasons/<int:pk>/standings/', StandingsView.as_view(), name='standings'),
]
