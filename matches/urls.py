from django.urls import path

from . import views

app_name = 'matches'

urlpatterns = [
    path('matches/<int:pk>/', views.MatchDetailView.as_view(), name='match_detail'),
    path('matches/<int:pk>/enter-result/', views.EnterResultView.as_view(), name='enter_result'),
    path('matches/<int:pk>/confirm-result/', views.ConfirmResultView.as_view(), name='confirm_result'),
    path('matches/<int:pk>/walkover/', views.WalkoverView.as_view(), name='walkover'),
    path('matches/<int:pk>/postpone/', views.PostponeView.as_view(), name='postpone'),
]
