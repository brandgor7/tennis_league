from django.urls import path

from . import views

app_name = 'matches'

urlpatterns = [
    path('seasons/<slug:slug>/matches/<int:pk>/', views.MatchDetailView.as_view(), name='match_detail'),
    path('seasons/<slug:slug>/matches/<int:pk>/enter-result/', views.EnterResultView.as_view(), name='enter_result'),
    path('seasons/<slug:slug>/matches/<int:pk>/edit-result/', views.EditResultView.as_view(), name='edit_result'),
    path('seasons/<slug:slug>/matches/<int:pk>/confirm-result/', views.ConfirmResultView.as_view(), name='confirm_result'),
    path('seasons/<slug:slug>/matches/<int:pk>/walkover/', views.WalkoverView.as_view(), name='walkover'),
    path('seasons/<slug:slug>/matches/<int:pk>/postpone/', views.PostponeView.as_view(), name='postpone'),
]
