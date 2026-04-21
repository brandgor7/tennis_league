from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import JsonResponse
from django.urls import path

from .models import User


class PlayerAddForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False, help_text='Optional.')
    set_password = forms.BooleanField(
        required=False,
        label='Set password now',
        help_text='Leave unchecked to create the account without a usable password.',
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput,
        required=False,
    )
    password2 = forms.CharField(
        label='Password confirmation',
        widget=forms.PasswordInput,
        required=False,
    )
    tier = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        help_text='Select a season first to see named tiers.',
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from leagues.models import Season
        self.fields['season'] = forms.ModelChoiceField(
            queryset=Season.objects.all().order_by('-year', 'name'),
            required=False,
            help_text='Optionally enrol this player in a season.',
            widget=forms.Select(attrs={'data-tiers-url': '../tiers-json/'}),
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('set_password'):
            p1 = cleaned.get('password1', '')
            p2 = cleaned.get('password2', '')
            if not p1:
                self.add_error('password1', 'Enter a password.')
            elif p1 != p2:
                self.add_error('password2', 'Passwords do not match.')
        return cleaned

    class Media:
        js = ('js/admin_add_player.js',)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    add_form = PlayerAddForm
    add_form_template = None
    add_fieldsets = (
        ('Player Info', {
            'fields': ('first_name', 'last_name', 'username', 'email'),
        }),
        ('Password', {
            'fields': ('set_password', 'password1', 'password2'),
        }),
        ('Season', {
            'fields': ('season', 'tier'),
        }),
    )

    def get_urls(self):
        return [
            path('tiers-json/', self.admin_site.admin_view(self._tiers_json), name='accounts_user_tiers_json'),
        ] + super().get_urls()

    def _tiers_json(self, request):
        from leagues.models import Tier
        season_id = request.GET.get('season_id')
        if not season_id:
            return JsonResponse([], safe=False)
        tiers = list(
            Tier.objects.filter(season_id=season_id).order_by('number').values('number', 'name')
        )
        return JsonResponse(tiers, safe=False)

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        if form.cleaned_data.get('set_password'):
            obj.set_password(form.cleaned_data['password1'])
        else:
            obj.set_unusable_password()
        obj.save()

        season = form.cleaned_data.get('season')
        if season:
            from leagues.models import SeasonPlayer
            tier = form.cleaned_data.get('tier') or 1
            SeasonPlayer.objects.get_or_create(
                season=season, player=obj, defaults={'tier': tier}
            )
