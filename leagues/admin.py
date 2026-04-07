import base64
import csv
import datetime
import io
import re

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Season, SeasonPlayer, SiteConfig
from playoffs.generator import bracket_size_for, generate_bracket
from playoffs.models import PlayoffBracket
from standings.calculator import calculate_standings

_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
_JPEG_MAGIC = b'\xff\xd8\xff'
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


class SeasonPlayerInline(admin.TabularInline):
    model = SeasonPlayer
    extra = 1
    fields = ('player', 'tier', 'seed', 'is_active')
    autocomplete_fields = ('player',)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'status', 'schedule_type', 'num_tiers', 'sets_to_win', 'final_set_format', 'playoff_qualifiers_count')
    list_filter = ('status', 'year', 'final_set_format', 'walkover_rule')
    search_fields = ('name',)
    inlines = [SeasonPlayerInline]
    fieldsets = (
        (None, {'fields': ('name', 'year', 'status', 'display', 'num_tiers')}),
        ('Schedule', {'fields': ('schedule_type', 'schedule_display_mode', 'schedule_display_days')}),
        ('Match Format', {'fields': ('sets_to_win', 'games_to_win_set', 'final_set_format')}),
        ('Playoffs', {'fields': ('playoff_qualifiers_count',)}),
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
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        season = get_object_or_404(Season, pk=object_id)
        generate_urls = []
        for tier in range(1, season.num_tiers + 1):
            generate_urls.append({
                'tier': tier,
                'url': reverse('admin:leagues_season_generate_playoffs', args=[object_id, tier]),
            })
        extra_context['generate_playoff_urls'] = generate_urls
        extra_context['generate_schedule_url'] = reverse(
            'admin:leagues_season_generate_schedule', args=[object_id]
        )
        extra_context['import_players_url'] = reverse(
            'admin:leagues_season_import_players', args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def generate_schedule_view(self, request, season_id):
        from matches.models import Match
        from matches.scheduler import generate_schedule

        season = get_object_or_404(Season, pk=season_id)
        has_matches = Match.objects.filter(season=season, round=Match.ROUND_REGULAR).exists()

        tier_info = []
        for tier in range(1, season.num_tiers + 1):
            count = SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True).count()
            max_rounds = count - 1 + count % 2  # N-1 for even N, N for odd N
            tier_info.append({'tier': tier, 'player_count': count, 'max_rounds': max_rounds})

        error = None
        start_date_val = ''
        num_rounds_val = ''

        if request.method == 'POST' and not has_matches:
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
                try:
                    matches = generate_schedule(season, start_date, num_rounds)
                    messages.success(
                        request,
                        f'{len(matches)} match{"es" if len(matches) != 1 else ""} scheduled for {season}.',
                    )
                    return HttpResponseRedirect(
                        reverse('admin:leagues_season_change', args=[season_id])
                    )
                except ValueError as e:
                    error = str(e)

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'has_matches': has_matches,
            'tier_info': tier_info,
            'error': error,
            'start_date_val': start_date_val,
            'num_rounds_val': num_rounds_val,
            'title': f'Generate Schedule — {season.name}',
        }
        return render(request, 'leagues/generate_schedule.html', context)

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

    def generate_playoffs_view(self, request, season_id, tier):
        season = get_object_or_404(Season, pk=season_id)
        existing_bracket = PlayoffBracket.objects.filter(season=season, tier=tier).first()
        standings = calculate_standings(season, tier)
        max_q = min(season.playoff_qualifiers_count, len(standings))
        size = bracket_size_for(max_q)
        qualifiers = standings[:size]

        if request.method == 'POST' and not existing_bracket:
            try:
                generate_bracket(season, tier, request.user)
                messages.success(request, f'Tier {tier} playoff bracket generated successfully.')
                return HttpResponseRedirect(
                    reverse('leagues:playoffs_tier', kwargs={'pk': season_id, 'tier': tier})
                )
            except ValueError as e:
                messages.error(request, str(e))

        context = {
            **self.admin_site.each_context(request),
            'season': season,
            'tier': tier,
            'qualifiers': qualifiers,
            'bracket_size': size,
            'existing_bracket': existing_bracket,
            'title': f'Generate Tier {tier} Playoffs — {season.name}',
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
