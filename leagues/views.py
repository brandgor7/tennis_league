from django.shortcuts import redirect
from django.views.generic import ListView, DetailView

from .models import Season


def home(request):
    active_season = Season.objects.filter(status=Season.STATUS_ACTIVE).first()
    if active_season:
        # TODO Phase 5: redirect to 'leagues:standings' once that view exists.
        return redirect('leagues:season_detail', pk=active_season.pk)
    return redirect('leagues:season_list')


class SeasonListView(ListView):
    model = Season
    template_name = 'leagues/season_list.html'
    context_object_name = 'seasons'
    ordering = ['-year', 'name']


class SeasonDetailView(DetailView):
    model = Season
    template_name = 'leagues/season_detail.html'
    context_object_name = 'season'
