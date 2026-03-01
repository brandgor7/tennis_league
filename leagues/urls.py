from django.urls import path

from . import views

app_name = 'leagues'

urlpatterns = [
    path('seasons/', views.SeasonListView.as_view(), name='season_list'),
    path('seasons/<int:pk>/', views.SeasonDetailView.as_view(), name='season_detail'),
]
