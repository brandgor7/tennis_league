from django.urls import path

from . import views
from standings.views import StandingsView
from matches.views import MatchupsView, ResultsView

app_name = 'leagues'

urlpatterns = [
    path('seasons/', views.SeasonListView.as_view(), name='season_list'),
    path('seasons/<int:pk>/', views.SeasonDetailView.as_view(), name='season_detail'),
    path('seasons/<int:pk>/standings/', StandingsView.as_view(), name='standings'),
    path('seasons/<int:pk>/matchups/', MatchupsView.as_view(), name='matchups'),
    path('seasons/<int:pk>/results/', ResultsView.as_view(), name='results'),
]
