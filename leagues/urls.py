from django.urls import path

from . import views
from standings.views import StandingsView
from matches.views import MatchupsView, ResultsView
from playoffs.views import PlayoffListView, PlayoffBracketView

app_name = 'leagues'

urlpatterns = [
    path('seasons/', views.SeasonListView.as_view(), name='season_list'),
    path('seasons/<int:pk>/', views.SeasonDetailView.as_view(), name='season_detail'),
    path('seasons/<int:pk>/standings/', StandingsView.as_view(), name='standings'),
    path('seasons/<int:pk>/matchups/', MatchupsView.as_view(), name='matchups'),
    path('seasons/<int:pk>/results/', ResultsView.as_view(), name='results'),
    path('seasons/<int:pk>/playoffs/', PlayoffListView.as_view(), name='playoffs'),
    path('seasons/<int:pk>/playoffs/<int:tier>/', PlayoffBracketView.as_view(), name='playoffs_tier'),
    path('seasons/<int:pk>/players/', views.SeasonPlayerListView.as_view(), name='player_list'),
    path('seasons/<int:pk>/players/<int:player_pk>/', views.SeasonPlayerDetailView.as_view(), name='player_detail'),
]
