from .models import Season


def season_context(request):
    all_seasons = Season.objects.all()

    current_season = None
    if hasattr(request, 'resolver_match') and request.resolver_match:
        season_id = request.resolver_match.kwargs.get('pk')
        if season_id:
            try:
                current_season = Season.objects.get(pk=season_id)
            except Season.DoesNotExist:
                pass

    if current_season is None:
        current_season = all_seasons.filter(status=Season.STATUS_ACTIVE).first()

    return {
        'current_season': current_season,
        'all_seasons': all_seasons,
    }
