from django.db.models import Q

from .models import Season, SiteConfig


def season_context(request):
    # Skip on admin pages — avoid DB queries on every admin response.
    if request.path.startswith('/admin/'):
        return {}

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

    # Read the season slug from the URL when inside a season-scoped namespace.
    if resolver and resolver.namespace in ('leagues', 'matches'):
        season_slug = resolver.kwargs.get('slug')
        if season_slug:
            current_season = next((s for s in all_seasons if s.slug == season_slug), None)
            # Any season is accessible via direct URL regardless of display flag,
            # so fall back to a direct lookup if it wasn't in the visible list.
            if current_season is None:
                current_season = Season.objects.filter(slug=season_slug).first()

    if current_season is None:
        last_slug = request.COOKIES.get('last_season')
        if last_slug:
            current_season = next((s for s in all_seasons if s.slug == last_slug), None)
            if current_season is None:
                current_season = Season.objects.filter(slug=last_slug).first()

    if current_season is None:
        current_season = next(
            (s for s in all_seasons if s.status == Season.STATUS_ACTIVE), None
        )

    # Branding: season-level overrides take priority over the global SiteConfig fallback.
    config = SiteConfig.get()
    site_name = (current_season.site_name if current_season and current_season.site_name else None) or config.site_name
    logo_data_url = (current_season.logo_url if current_season else None) or config.logo_url

    return {
        'current_season': current_season,
        'all_seasons': all_seasons,
        'site_name': site_name,
        'logo_data_url': logo_data_url,
        'show_rules': current_season.show_rules if current_season else False,
    }
