from django.urls import path

from . import views
from standings.views import StandingsView
from matches.views import MatchupsView, ResultsView
from playoffs.views import PlayoffListView, PlayoffBracketView

app_name = 'leagues'

urlpatterns = [
    path('seasons/<slug:slug>/rules/', views.RulesView.as_view(), name='rules'),
    path('seasons/', views.SeasonListView.as_view(), name='season_list'),
    path('seasons/<slug:slug>/', views.SeasonDetailView.as_view(), name='season_detail'),
    path('seasons/<slug:slug>/standings/', StandingsView.as_view(), name='standings'),
    path('seasons/<slug:slug>/matchups/', MatchupsView.as_view(), name='matchups'),
    path('seasons/<slug:slug>/results/', ResultsView.as_view(), name='results'),
    path('seasons/<slug:slug>/playoffs/', PlayoffListView.as_view(), name='playoffs'),
    path('seasons/<slug:slug>/playoffs/<int:tier>/', PlayoffBracketView.as_view(), name='playoffs_tier'),
    path('seasons/<slug:slug>/players/<str:username>/', views.SeasonPlayerDetailView.as_view(), name='player_detail'),
]
