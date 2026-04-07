from django.db.models import Q

from .models import Season, SiteConfig


def season_context(request):
    # Skip on admin pages — avoid DB queries on every admin response.
    if request.path.startswith('/admin/'):
        return {}

    config = SiteConfig.get()
    site_name = config.site_name
    logo_data_url = config.logo_url

    user = request.user

    # Build the seasons visible in the dropdown.
    # Staff see everything; players see seasons where display=True or they are enrolled;
    # anonymous users see only display=True seasons.
    if user.is_authenticated and user.is_staff:
        all_seasons = list(Season.objects.all())
    elif user.is_authenticated:
        all_seasons = list(
            Season.objects.filter(
                Q(display=True) | Q(season_players__player=user, season_players__is_active=True)
            ).distinct()
        )
    else:
        all_seasons = list(Season.objects.filter(display=True))

    current_season = None
    resolver = getattr(request, 'resolver_match', None)

    # Only use the URL slug when we are inside the 'leagues' namespace, so a
    # match pk at /matches/42/ never accidentally selects Season 42.
    if resolver and resolver.namespace == 'leagues':
        season_slug = resolver.kwargs.get('slug')
        if season_slug:
            current_season = next((s for s in all_seasons if s.slug == season_slug), None)
            # Any season is accessible via direct URL regardless of display flag,
            # so fall back to a direct lookup if it wasn't in the visible list.
            if current_season is None:
                current_season = Season.objects.filter(slug=season_slug).first()

    if current_season is None:
        current_season = next(
            (s for s in all_seasons if s.status == Season.STATUS_ACTIVE), None
        )

    return {
        'current_season': current_season,
        'all_seasons': all_seasons,
        'site_name': site_name,
        'logo_data_url': logo_data_url,
    }
