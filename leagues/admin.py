import base64
import csv
import datetime
import io
import re

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Season, SeasonPlayer, SiteConfig, Tier
from matches.models import Match
from matches.scheduler import generate_schedule, remaining_rounds_count
from playoffs.generator import bracket_size_for, generate_bracket
from playoffs.models import PlayoffBracket
from standings.calculator import calculate_standings

_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
_JPEG_MAGIC = b'\xff\xd8\xff'
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


class TierInline(admin.TabularInline):
    model = Tier
    extra = 0
    fields = ('number', 'name')


class SeasonPlayerInline(admin.TabularInline):
    model = SeasonPlayer
    extra = 1
    fields = ('player', 'tier', 'seed', 'is_active')
    autocomplete_fields = ('player',)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'status', 'schedule_type', 'sets_to_win', 'final_set_format', 'playoff_qualifiers_count')
    list_filter = ('status', 'year', 'final_set_format', 'walkover_rule')
    search_fields = ('name',)
    inlines = [TierInline, SeasonPlayerInline]
    fieldsets = (
        (None, {'fields': ('name', 'year', 'status', 'display')}),
        ('Schedule', {'fields': ('schedule_type', 'schedule_display_mode', 'schedule_display_days')}),
        ('Match Format', {'fields': ('sets_to_win', 'games_to_win_set', 'final_set_format')}),
        ('Playoffs', {'fields': ('playoffs_enabled', 'playoff_qualifiers_count')}),
        ('Points', {'fields': ('points_for_win', 'points_for_loss', 'points_for_walkover_loss')}),
        ('Rules', {'fields': ('walkover_rule', 'postponement_deadline', 'grace_period_days')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:season_id>/generate-playoffs/<int:tier>/',
                self.admin_site.admin_view(self.generate_playoffs_view),
                name='leagues_season_generate_playoffs',
            ),
            path(
                '<int:season_id>/generate-schedule/',
                self.admin_site.admin_view(self.generate_schedule_view),
                name='leagues_season_generate_schedule',
            ),
            path(
                '<int:season_id>/import-players/',
                self.admin_site.admin_view(self.import_players_view),
                name='leagues_season_import_players',
            ),
            path(
                '<int:season_id>/copy-players/',
                self.admin_site.admin_view(self.copy_players_view),
                name='leagues_season_copy_players',
            ),
            path(
                '<int:season_id>/schedule-match/',
                self.admin_site.admin_view(self.schedule_match_view),
                name='leagues_season_schedule_match',
            ),
            path(
                '<int:season_id>/schedule-match/players/',
                self.admin_site.admin_view(self.schedule_match_players_view),
                name='leagues_season_schedule_match_players',
            ),
            path(
                '<int:season_id>/schedule-match/matchups/',
                self.admin_site.admin_view(self.schedule_match_matchups_view),
                name='leagues_season_schedule_match_matchups',
            ),
            path(
                '<int:season_id>/delete-match/',
                self.admin_site.admin_view(self.delete_match_view),
                name='leagues_season_delete_match',
            ),
            path(
                '<int:season_id>/delete-match/matches/',
                self.admin_site.admin_view(self.delete_match_matches_view),
                name='leagues_season_delete_match_matches',
            ),
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        season = get_object_or_404(Season.objects.prefetch_related('tiers'), pk=object_id)
        generate_urls = []
        if season.playoffs_enabled:
            for tier in range(1, season.num_tiers + 1):
                generate_urls.append({
                    'tier_name': season.tier_name(tier),
                    'url': reverse('admin:leagues_season_generate_playoffs', args=[object_id, tier]),
                })
        extra_context['generate_playoff_urls'] = generate_urls
        extra_context['generate_schedule_url'] = reverse(
            'admin:leagues_season_generate_schedule', args=[object_id]
        )
        extra_context['import_players_url'] = reverse(
            'admin:leagues_season_import_players', args=[object_id]
        )
        extra_context['copy_players_url'] = reverse(
            'admin:leagues_season_copy_players', args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def generate_schedule_view(self, request, season_id):
        season = get_object_or_404(Season.objects.prefetch_related('tiers'), pk=season_id)
        tier_range = range(1, season.num_tiers + 1)

        tier_info = []
        for tier in tier_range:
            count = SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True).count()
            max_rounds = count - 1 + count % 2  # N-1 for even N, N for odd N
            remaining = remaining_rounds_count(season, tier)
            tier_info.append({
                'tier': tier,
                'tier_name': season.tier_name(tier),
                'player_count': count,
                'max_rounds': max_rounds,
                'remaining_rounds': remaining,
            })

        all_exhausted = all(row['remaining_rounds'] == 0 for row in tier_info)

        schedule_analysis = self._build_schedule_analysis(season, tier_range)

        error = None
        start_date_val = ''
        num_rounds_val = ''

        if request.method == 'POST':
            start_date_val = request.POST.get('start_date', '')
            num_rounds_val = request.POST.get('num_rounds', '')
            start_date = None

            try:
                start_date = datetime.date.fromisoformat(start_date_val)
            except (ValueError, TypeError):
                error = 'Please enter a valid start date.'

            if not error:
                try:
                    num_rounds = int(num_rounds_val)
                    if num_rounds < 1:
                        raise ValueError
                except (ValueError, TypeError):
                    error = 'Number of rounds must be a positive integer.'

            if not error:
                matches = generate_schedule(season, start_date, num_rounds)
                if matches:
                    messages.success(
                        request,
                        f'{len(matches)} match{"es" if len(matches) != 1 else ""} scheduled for {season}.',
                    )
                else:
                    messages.warning(request, 'No new matches were scheduled — all rounds are already booked.')
                return HttpResponseRedirect(
                    reverse('admin:leagues_season_change', args=[season_id])
                )

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'tier_info': tier_info,
            'all_exhausted': all_exhausted,
            'schedule_analysis': schedule_analysis,
            'error': error,
            'start_date_val': start_date_val,
            'num_rounds_val': num_rounds_val,
            'title': f'Analyze / Generate Schedule — {season.name}',
        }
        return render(request, 'leagues/generate_schedule.html', context)

    def _match_count_map(self, season, tier, tier_players):
        """Return {player_id: scheduled_match_count} for all players in tier_players."""
        match_pairs = list(
            Match.objects.filter(season=season, tier=tier, round=Match.ROUND_REGULAR)
            .values_list('player1_id', 'player2_id')
        )
        count_map = {sp.player_id: 0 for sp in tier_players}
        for p1_id, p2_id in match_pairs:
            if p1_id in count_map:
                count_map[p1_id] += 1
            if p2_id in count_map:
                count_map[p2_id] += 1
        return count_map

    def schedule_match_players_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        try:
            tier = int(request.GET.get('tier', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid tier'}, status=400)

        tier_players = list(
            SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
            .select_related('player')
        )
        count_map = self._match_count_map(season, tier, tier_players)

        players = sorted(
            [
                {
                    'id': sp.player_id,
                    'name': sp.player.get_full_name() or sp.player.username,
                    'match_count': count_map[sp.player_id],
                }
                for sp in tier_players
            ],
            key=lambda x: (x['match_count'], x['name']),
        )
        return JsonResponse({'players': players})

    def schedule_match_matchups_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        try:
            tier = int(request.GET.get('tier', ''))
            player_id = int(request.GET.get('player', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid parameters'}, status=400)

        tier_players = list(
            SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
            .select_related('player')
        )
        player_map = {sp.player_id: sp.player for sp in tier_players}
        if player_id not in player_map:
            return JsonResponse({'error': 'Player not found'}, status=400)

        count_map = self._match_count_map(season, tier, tier_players)

        played_opponents = set()
        for p1_id, p2_id in Match.objects.filter(
            season=season, tier=tier, round=Match.ROUND_REGULAR
        ).values_list('player1_id', 'player2_id'):
            if player_id == p1_id:
                played_opponents.add(p2_id)
            elif player_id == p2_id:
                played_opponents.add(p1_id)

        not_played = []
        already_played = []
        for sp in tier_players:
            if sp.player_id == player_id:
                continue
            entry = {
                'id': sp.player_id,
                'name': sp.player.get_full_name() or sp.player.username,
                'match_count': count_map[sp.player_id],
            }
            if sp.player_id in played_opponents:
                already_played.append(entry)
            else:
                not_played.append(entry)

        not_played.sort(key=lambda x: (x['match_count'], x['name']))
        already_played.sort(key=lambda x: (x['match_count'], x['name']))
        return JsonResponse({'not_played': not_played, 'already_played': already_played})

    def schedule_match_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        try:
            tier = int(request.POST.get('tier', ''))
            player1_id = int(request.POST.get('player1', ''))
            player2_id = int(request.POST.get('player2', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid parameters'}, status=400)

        if player1_id == player2_id:
            return JsonResponse({'error': 'Cannot schedule a player against themselves'}, status=400)

        valid_ids = set(
            SeasonPlayer.objects.filter(
                season=season, player_id__in=[player1_id, player2_id],
                tier=tier, is_active=True,
            ).values_list('player_id', flat=True)
        )
        if player1_id not in valid_ids:
            return JsonResponse({'error': 'Player 1 not found in tier'}, status=400)
        if player2_id not in valid_ids:
            return JsonResponse({'error': 'Player 2 not found in tier'}, status=400)

        scheduled_date = None
        scheduled_date_str = request.POST.get('scheduled_date', '').strip()
        if scheduled_date_str:
            try:
                scheduled_date = datetime.date.fromisoformat(scheduled_date_str)
            except ValueError:
                return JsonResponse({'error': 'Invalid date'}, status=400)

        match = Match.objects.create(
            season=season,
            player1_id=player1_id,
            player2_id=player2_id,
            tier=tier,
            round=Match.ROUND_REGULAR,
            scheduled_date=scheduled_date,
            status=Match.STATUS_SCHEDULED,
        )
        return JsonResponse({'success': True, 'match_id': match.id})

    def delete_match_matches_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        try:
            tier = int(request.GET.get('tier', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid tier'}, status=400)

        matches = (
            Match.objects.filter(
                season=season, tier=tier, round=Match.ROUND_REGULAR,
                status=Match.STATUS_SCHEDULED,
            )
            .select_related('player1', 'player2')
            .order_by('scheduled_date', 'player1__last_name', 'player1__first_name')
        )

        result = []
        for m in matches:
            p1 = (m.player1.get_full_name() or m.player1.username) if m.player1 else '?'
            p2 = (m.player2.get_full_name() or m.player2.username) if m.player2 else '?'
            if m.scheduled_date:
                d = m.scheduled_date
                date_str = f'{d.strftime("%b")} {d.day}, {d.year}'
            else:
                date_str = 'No date'
            result.append({
                'id': m.id,
                'label': f'{date_str} — {p1} vs {p2}',
            })

        return JsonResponse({'matches': result})

    def delete_match_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        try:
            match_id = int(request.POST.get('match_id', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid match ID'}, status=400)

        try:
            match = Match.objects.get(
                pk=match_id, season=season,
                round=Match.ROUND_REGULAR, status=Match.STATUS_SCHEDULED,
            )
        except Match.DoesNotExist:
            return JsonResponse({'error': 'Match not found or cannot be deleted'}, status=400)

        match.delete()
        return JsonResponse({'success': True})

    def _build_schedule_analysis(self, season, tier_range):
        date_tier_qs = (
            Match.objects.filter(season=season, round=Match.ROUND_REGULAR)
            .exclude(scheduled_date=None)
            .values('scheduled_date', 'tier')
            .annotate(count=Count('id'))
            .order_by('scheduled_date', 'tier')
        )

        date_tier_map = {}
        for row in date_tier_qs:
            d = row['scheduled_date']
            t = row['tier']
            date_tier_map.setdefault(d, {})[t] = row['count']

        if not date_tier_map:
            return None

        tier_names = [season.tier_name(t) for t in tier_range]
        multi_tier = len(tier_names) > 1

        date_rows = []
        for d in sorted(date_tier_map.keys()):
            tier_counts = [date_tier_map[d].get(t, 0) for t in tier_range]
            date_rows.append({
                'date': d,
                'tier_counts': tier_counts,
                'total': sum(tier_counts),
            })

        totals = [sum(row['tier_counts'][i] for row in date_rows) for i in range(len(tier_names))]
        grand_total = sum(totals)

        behind_by_tier = []
        for tier in tier_range:
            tier_players = list(
                SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
                .select_related('player')
            )
            if not tier_players:
                continue

            count_map = self._match_count_map(season, tier, tier_players)
            max_count = max(count_map.values()) if count_map else 0
            if max_count == 0:
                continue

            behind = sorted(
                [
                    {
                        'player': sp.player,
                        'count': count_map[sp.player_id],
                        'deficit': max_count - count_map[sp.player_id],
                    }
                    for sp in tier_players
                    if count_map[sp.player_id] < max_count
                ],
                key=lambda x: (x['count'], x['player'].get_full_name()),
            )
            if behind:
                behind_by_tier.append({
                    'tier_name': season.tier_name(tier),
                    'max_count': max_count,
                    'players': behind,
                })

        return {
            'tier_names': tier_names,
            'multi_tier': multi_tier,
            'date_rows': date_rows,
            'totals': totals,
            'grand_total': grand_total,
            'behind_by_tier': behind_by_tier,
        }

    def import_players_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        User = get_user_model()
        results = None
        error = None

        if request.method == 'POST':
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                error = 'Please select a CSV file to upload.'
            elif not csv_file.name.endswith('.csv'):
                error = 'Uploaded file must be a .csv file.'
            else:
                try:
                    text = csv_file.read().decode('utf-8-sig')
                    reader = csv.DictReader(io.StringIO(text))
                    results = {'created': [], 'updated': [], 'skipped': [], 'errors': []}

                    tier_map = {}
                    for header in reader.fieldnames or []:
                        stripped = header.strip()
                        match = re.fullmatch(r'(?:tier\s*)?(\d+)', stripped, re.IGNORECASE)
                        if match:
                            tier_map[header] = int(match.group(1))

                    if not tier_map:
                        error = 'No valid tier columns found. Headers must be a tier number (e.g. "1", "Tier 1", "tier1").'
                    else:
                        with transaction.atomic():
                            for row in reader:
                                for header, tier_num in tier_map.items():
                                    name = (row.get(header) or '').strip()
                                    if not name:
                                        continue

                                    parts = name.split(None, 1)
                                    first_name = parts[0]
                                    last_name = parts[1] if len(parts) > 1 else ''

                                    matched = list(User.objects.filter(
                                        first_name__iexact=first_name,
                                        last_name__iexact=last_name,
                                    )[:2])
                                    if len(matched) > 1:
                                        results['errors'].append(
                                            f'"{name}" matches multiple users — skipped.'
                                        )
                                        continue

                                    user = matched[0] if matched else None
                                    if user is None:
                                        base_username = (first_name + last_name).lower()
                                        username = base_username
                                        n = 1
                                        while User.objects.filter(username=username).exists():
                                            username = f'{base_username}{n}'
                                            n += 1
                                        user = User.objects.create_user(
                                            username=username,
                                            first_name=first_name,
                                            last_name=last_name,
                                        )
                                        SeasonPlayer.objects.create(
                                            season=season, player=user, tier=tier_num
                                        )
                                        results['created'].append(
                                            f'{name} (Tier {tier_num}, username: {user.username})'
                                        )
                                    else:
                                        sp, created = SeasonPlayer.objects.get_or_create(
                                            season=season, player=user,
                                            defaults={'tier': tier_num},
                                        )
                                        if created:
                                            results['created'].append(f'{name} (Tier {tier_num})')
                                        elif sp.tier != tier_num:
                                            sp.tier = tier_num
                                            sp.save(update_fields=['tier'])
                                            results['updated'].append(
                                                f'{name} moved to Tier {tier_num}'
                                            )
                                        else:
                                            results['skipped'].append(f'{name} (already in Tier {tier_num})')

                        messages.success(
                            request,
                            f'Import complete: {len(results["created"])} created, '
                            f'{len(results["updated"])} updated, '
                            f'{len(results["skipped"])} skipped, '
                            f'{len(results["errors"])} errors.',
                        )
                except (csv.Error, UnicodeDecodeError, ValueError) as exc:
                    error = f'Failed to parse CSV: {exc}'

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'error': error,
            'results': results,
            'title': f'Import Players — {season.name}',
        }
        return render(request, 'leagues/import_players.html', context)

    def copy_players_view(self, request, season_id):
        season = get_object_or_404(Season, pk=season_id)
        error = None

        if request.method == 'POST':
            source_id = request.POST.get('source_season')
            try:
                source_season = Season.objects.get(pk=source_id)
            except (Season.DoesNotExist, ValueError, TypeError):
                error = 'Please select a valid season.'
            else:
                valid_tiers = {t.number for t in season.tiers.all()} or {1}
                source_players = SeasonPlayer.objects.filter(
                    season=source_season, is_active=True
                ).select_related('player')
                added = skipped = tier_skipped = 0
                with transaction.atomic():
                    for sp in source_players:
                        if sp.tier not in valid_tiers:
                            tier_skipped += 1
                            continue
                        _, created = SeasonPlayer.objects.get_or_create(
                            season=season,
                            player=sp.player,
                            defaults={'tier': sp.tier},
                        )
                        if created:
                            added += 1
                        else:
                            skipped += 1

                parts = [f'{added} added', f'{skipped} already enrolled']
                if tier_skipped:
                    parts.append(f'{tier_skipped} skipped (tier not in this season)')
                messages.success(request, f'Copy complete: {", ".join(parts)}.')
                return HttpResponseRedirect(
                    reverse('admin:leagues_season_change', args=[season_id])
                )

        other_seasons = Season.objects.exclude(pk=season_id).order_by('-year', 'name')
        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'other_seasons': other_seasons,
            'error': error,
            'back_url': reverse('admin:leagues_season_change', args=[season_id]),
            'title': f'Copy Players — {season.name}',
        }
        return render(request, 'leagues/copy_players_from_season.html', context)

    def generate_playoffs_view(self, request, season_id, tier):
        season = get_object_or_404(Season, pk=season_id)
        existing_bracket = PlayoffBracket.objects.filter(season=season, tier=tier).first()
        standings = calculate_standings(season, tier)
        max_q = min(season.playoff_qualifiers_count, len(standings))
        size = bracket_size_for(max_q)
        qualifiers = standings[:size]

        tier_name = season.tier_name(tier)
        if request.method == 'POST' and not existing_bracket:
            try:
                generate_bracket(season, tier, request.user)
                messages.success(request, f'{tier_name} playoff bracket generated successfully.')
                return HttpResponseRedirect(
                    reverse('leagues:playoffs_tier', kwargs={'pk': season_id, 'tier': tier})
                )
            except ValueError as e:
                messages.error(request, str(e))

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'tier': tier,
            'tier_name': tier_name,
            'qualifiers': qualifiers,
            'bracket_size': size,
            'existing_bracket': existing_bracket,
            'title': f'Generate {tier_name} Playoffs — {season.name}',
        }
        return render(request, 'playoffs/generate_playoffs.html', context)


@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(admin.ModelAdmin):
    list_display = ('player', 'season', 'tier', 'seed', 'is_active', 'joined_at')
    list_filter = ('season', 'tier', 'is_active')
    search_fields = ('player__username', 'player__first_name', 'player__last_name', 'season__name')
    autocomplete_fields = ('player', 'season')


class SiteConfigForm(forms.ModelForm):
    logo_upload = forms.FileField(
        required=False,
        label='Upload logo (PNG or JPEG)',
        help_text='Max 2 MB. Replaces the current logo.',
    )
    clear_logo = forms.BooleanField(
        required=False,
        label='Remove current logo',
        help_text='Tick to revert to the default tennis-ball icon.',
    )

    class Meta:
        model = SiteConfig
        fields = ('site_name',)

    def clean_logo_upload(self):
        f = self.cleaned_data.get('logo_upload')
        if not f:
            return None
        if f.size > _MAX_LOGO_BYTES:
            raise forms.ValidationError('Logo must be under 2 MB.')
        header = f.read(8)
        f.seek(0)
        if header[:8] == _PNG_MAGIC:
            mime = 'image/png'
        elif header[:3] == _JPEG_MAGIC:
            mime = 'image/jpeg'
        else:
            raise forms.ValidationError('File must be a PNG or JPEG image.')
        return (mime, f.read())

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('clear_logo'):
            instance.logo = ''
        elif self.cleaned_data.get('logo_upload'):
            mime, data = self.cleaned_data['logo_upload']
            instance.logo = f'data:{mime};base64,{base64.b64encode(data).decode()}'
        if commit:
            instance.save()
        return instance


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    form = SiteConfigForm
    fieldsets = (
        (None, {'fields': ('site_name',)}),
        ('Logo', {'fields': ('logo_preview', 'logo_upload', 'clear_logo')}),
    )
    readonly_fields = ('logo_preview',)

    def logo_preview(self, obj):
        if not obj or not obj.logo:
            return '(none — default tennis-ball icon will be shown)'
        return format_html(
            '<img src="{}" alt="Current logo"'
            ' style="max-height:80px;background:#1B3D2B;padding:8px;border-radius:4px;">',
            obj.logo,
        )
    logo_preview.short_description = 'Current logo'

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _ = SiteConfig.objects.get_or_create(pk=1)
        return HttpResponseRedirect(
            reverse('admin:leagues_siteconfig_change', args=[obj.pk])
        )
