from .models import Season


def season_context(request):
    # Skip on admin pages — avoid DB queries on every admin response.
    if request.path.startswith('/admin/'):
        return {}

    # One DB query, evaluated eagerly so current_season can be resolved
    # from the same result set without a second round-trip.
    all_seasons = list(Season.objects.all())

    current_season = None
    resolver = getattr(request, 'resolver_match', None)

    # Only use the URL pk when we are inside the 'leagues' namespace, so a
    # match pk at /matches/42/ never accidentally selects Season 42.
    if resolver and resolver.namespace == 'leagues':
        season_id = resolver.kwargs.get('pk')
        if season_id:
            current_season = next((s for s in all_seasons if s.pk == season_id), None)

    if current_season is None:
        current_season = next(
            (s for s in all_seasons if s.status == Season.STATUS_ACTIVE), None
        )

    return {
        'current_season': current_season,
        'all_seasons': all_seasons,
    }
