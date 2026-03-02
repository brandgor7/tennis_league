from django.urls import path

from . import views

app_name = 'matches'

urlpatterns = [
    path('matches/<int:pk>/', views.MatchDetailView.as_view(), name='match_detail'),
]
