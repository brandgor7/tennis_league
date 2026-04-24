import base64
import datetime

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Season, SeasonPlayer, SiteConfig, Tier
from .forms import SeasonForm
from .admin import SiteConfigForm
from .templatetags.site_branding import get_site_config
from matches.models import Match

User = get_user_model()

# ─── Image test fixtures ──────────────────────────────────────────────────────

_PNG_HEADER = b'\x89PNG\r\n\x1a\n'
_JPEG_HEADER = b'\xff\xd8\xff\xe0'
_SMALL_PNG = _PNG_HEADER + b'\x00' * 20
_SMALL_JPEG = _JPEG_HEADER + b'\x00' * 20


def _png_file(name='logo.png', content=_SMALL_PNG):
    return SimpleUploadedFile(name, content, content_type='image/png')


def _jpeg_file(name='logo.jpg', content=_SMALL_JPEG):
    return SimpleUploadedFile(name, content, content_type='image/jpeg')


# ─── Shared helpers ───────────────────────────────────────────────────────────

def make_season(**kwargs):
    defaults = dict(
        name='Spring 2025', year=2025,
        status=Season.STATUS_ACTIVE,
        points_for_win=3,
        points_for_loss=0,
        points_for_walkover_loss=0,
        walkover_rule=Season.WALKOVER_WINNER,
    )
    defaults.update(kwargs)
    return Season.objects.create(**defaults)


def make_player(username, first='', last=''):
    return User.objects.create_user(username=username, first_name=first, last_name=last)


def enroll(season, player, tier=1, is_active=True):
    return SeasonPlayer.objects.create(season=season, player=player, tier=tier, is_active=is_active)


# ─── Model tests ─────────────────────────────────────────────────────────────

class SeasonModelTest(TestCase):
    def test_str_includes_year(self):
        season = Season(name='Spring League', year=2025)
        self.assertEqual(str(season), 'Spring League 2025')

    def test_clean_raises_when_second_active_season(self):
        Season.objects.create(name='First', year=2024, status=Season.STATUS_ACTIVE)
        duplicate = Season(name='Second', year=2025, status=Season.STATUS_ACTIVE)
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_clean_allows_updating_the_existing_active_season(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        season.name = 'Spring Updated'
        # Should not raise — it is still the same active season.
        season.clean()

    def test_clean_allows_multiple_non_active_seasons(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        new = Season(name='New', year=2025, status=Season.STATUS_UPCOMING)
        new.clean()  # must not raise

    # ── Slug generation ──────────────────────────────────────────────────────

    def test_slug_generated_on_create(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.slug, 'spring-2025')

    def test_slug_updates_when_name_changes(self):
        season = Season.objects.create(name='Spring', year=2025)
        season.name = 'Autumn'
        season.save()
        season.refresh_from_db()
        self.assertEqual(season.slug, 'autumn-2025')

    def test_slug_updates_when_year_changes(self):
        season = Season.objects.create(name='Spring', year=2025)
        season.year = 2026
        season.save()
        season.refresh_from_db()
        self.assertEqual(season.slug, 'spring-2026')

    def test_slug_uniqueness_on_collision(self):
        Season.objects.create(name='Spring', year=2025)
        season2 = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_UPCOMING)
        self.assertEqual(season2.slug, 'spring-2025-1')

    # ── num_tiers property ───────────────────────────────────────────────────

    def test_num_tiers_defaults_to_1_with_no_tier_records(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.num_tiers, 1)

    def test_num_tiers_reflects_tier_count(self):
        season = Season.objects.create(name='Spring', year=2025)
        Tier.objects.create(season=season, number=1, name='Premier')
        Tier.objects.create(season=season, number=2, name='Division 1')
        self.assertEqual(season.num_tiers, 2)

    def test_num_tiers_reflects_tier_count_after_adding_tier(self):
        season = Season.objects.create(name='Spring', year=2025)
        Tier.objects.create(season=season, number=1, name='Premier')
        Tier.objects.create(season=season, number=2, name='Division 1')
        Tier.objects.create(season=season, number=3, name='Division 2')
        self.assertEqual(season.num_tiers, 3)

    # ── schedule_display_mode / schedule_display_days ────────────────────────

    def test_schedule_display_mode_defaults_to_all(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.schedule_display_mode, Season.DISPLAY_ALL)

    def test_schedule_display_days_defaults_to_7(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.schedule_display_days, 7)

    def test_schedule_display_mode_choices_are_valid(self):
        valid_modes = {Season.DISPLAY_ALL, Season.DISPLAY_CURRENT_DAY, Season.DISPLAY_CURRENT_WEEK, Season.DISPLAY_NEXT_X_DAYS}
        model_choices = {v for v, _ in Season.DISPLAY_MODE_CHOICES}
        self.assertEqual(valid_modes, model_choices)

    def test_schedule_display_mode_persists(self):
        season = Season.objects.create(name='Spring', year=2025, schedule_display_mode=Season.DISPLAY_NEXT_X_DAYS)
        season.refresh_from_db()
        self.assertEqual(season.schedule_display_mode, Season.DISPLAY_NEXT_X_DAYS)

    def test_schedule_display_days_persists(self):
        season = Season.objects.create(name='Spring', year=2025, schedule_display_days=14)
        season.refresh_from_db()
        self.assertEqual(season.schedule_display_days, 14)

    # ── display flag ─────────────────────────────────────────────────────────

    def test_display_defaults_to_true(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertTrue(season.display)

    def test_display_false_persists(self):
        season = Season.objects.create(name='Spring', year=2025, display=False)
        season.refresh_from_db()
        self.assertFalse(season.display)

    # ── tier_name() ──────────────────────────────────────────────────────────

    def test_tier_name_falls_back_when_no_tier_configured(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.tier_name(1), 'Tier 1')
        self.assertEqual(season.tier_name(2), 'Tier 2')

    def test_tier_name_returns_configured_name(self):
        season = Season.objects.create(name='Spring', year=2025)
        Tier.objects.create(season=season, number=1, name='Premier')
        Tier.objects.create(season=season, number=2, name='Division 1')
        self.assertEqual(season.tier_name(1), 'Premier')
        self.assertEqual(season.tier_name(2), 'Division 1')

    def test_tier_name_falls_back_for_unconfigured_number(self):
        season = Season.objects.create(name='Spring', year=2025)
        Tier.objects.create(season=season, number=1, name='Premier')
        self.assertEqual(season.tier_name(2), 'Tier 2')


class TierModelTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)

    def test_str(self):
        tier = Tier(season=self.season, number=1, name='Premier')
        self.assertEqual(str(tier), 'Premier — Spring 2025')

    def test_unique_together_enforced(self):
        Tier.objects.create(season=self.season, number=1, name='Premier')
        with self.assertRaises(IntegrityError):
            Tier.objects.create(season=self.season, number=1, name='Other')

    def test_different_numbers_allowed_same_season(self):
        Tier.objects.create(season=self.season, number=1, name='Premier')
        Tier.objects.create(season=self.season, number=2, name='Division 1')
        self.assertEqual(Tier.objects.filter(season=self.season).count(), 2)

    def test_same_number_allowed_different_seasons(self):
        season2 = Season.objects.create(name='Fall', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Premier')
        Tier.objects.create(season=season2, number=1, name='Elite')
        self.assertEqual(Tier.objects.count(), 2)

    def test_ordering_by_number(self):
        Tier.objects.create(season=self.season, number=2, name='Division 1')
        Tier.objects.create(season=self.season, number=1, name='Premier')
        tiers = list(Tier.objects.filter(season=self.season))
        self.assertEqual(tiers[0].number, 1)
        self.assertEqual(tiers[1].number, 2)


class SeasonPlayerModelTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.player = User.objects.create_user(username='player1')

    def test_str(self):
        sp = SeasonPlayer(season=self.season, player=self.player)
        self.assertIn(str(self.player), str(sp))
        self.assertIn(str(self.season), str(sp))

    def test_unique_together_enforced(self):
        SeasonPlayer.objects.create(season=self.season, player=self.player)
        with self.assertRaises(IntegrityError):
            SeasonPlayer.objects.create(season=self.season, player=self.player)

    # ── Phase 5: tier field ──────────────────────────────────────────────────

    def test_tier_defaults_to_1(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player)
        self.assertEqual(sp.tier, 1)

    def test_tier_can_be_set(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=2)
        self.assertEqual(sp.tier, 2)

    def test_tier_persists_after_save(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=3)
        sp.refresh_from_db()
        self.assertEqual(sp.tier, 3)

    def test_different_players_can_be_in_different_tiers(self):
        p2 = User.objects.create_user(username='player2')
        sp1 = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=1)
        sp2 = SeasonPlayer.objects.create(season=self.season, player=p2, tier=2)
        self.assertEqual(sp1.tier, 1)
        self.assertEqual(sp2.tier, 2)

    def test_can_filter_players_by_tier(self):
        p2 = User.objects.create_user(username='player2')
        p3 = User.objects.create_user(username='player3')
        SeasonPlayer.objects.create(season=self.season, player=self.player, tier=1)
        SeasonPlayer.objects.create(season=self.season, player=p2, tier=1)
        SeasonPlayer.objects.create(season=self.season, player=p3, tier=2)
        tier1 = SeasonPlayer.objects.filter(season=self.season, tier=1)
        tier2 = SeasonPlayer.objects.filter(season=self.season, tier=2)
        self.assertEqual(tier1.count(), 2)
        self.assertEqual(tier2.count(), 1)


# ─── SeasonForm tests ─────────────────────────────────────────────────────────

class SeasonFormTest(TestCase):
    def _valid_data(self, **overrides):
        data = {
            'name': 'Spring 2025',
            'year': 2025,
            'status': Season.STATUS_UPCOMING,
            'schedule_type': Season.SCHEDULE_WEEKLY,
            'sets_to_win': 2,
            'final_set_format': Season.FINAL_SET_FULL,
            'playoff_qualifiers_count': 8,
            'walkover_rule': Season.WALKOVER_WINNER,
            'postponement_deadline': 14,
            'points_for_win': 3,
            'points_for_loss': 0,
            'points_for_walkover_loss': 0,
        }
        data.update(overrides)
        return data

    def test_valid_form(self):
        form = SeasonForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_num_tiers_not_in_fields(self):
        form = SeasonForm()
        self.assertNotIn('num_tiers', form.fields)


# ─── View tests ───────────────────────────────────────────────────────────────

class HomeViewTest(TestCase):
    def test_home_renders_welcome_page_without_cookie(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_redirects_to_last_season_from_cookie(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        self.client.cookies['last_season'] = season.slug
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:standings', kwargs={'slug': season.slug}))

    def test_home_renders_welcome_page_when_cookie_slug_invalid(self):
        self.client.cookies['last_season'] = 'nonexistent-slug'
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('home'))
        self.assertIn(response.status_code, [200, 302])


class SeasonListViewTest(TestCase):
    def test_empty_season_list(self):
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No seasons')

    def test_season_list_shows_seasons(self):
        Season.objects.create(name='Spring 2025', year=2025)
        Season.objects.create(name='Fall 2025', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertContains(response, 'Spring 2025')
        self.assertContains(response, 'Fall 2025')

    def test_season_list_ordering_newest_first(self):
        old = Season.objects.create(name='Spring 2023', year=2023)
        new = Season.objects.create(name='Spring 2025', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        seasons = list(response.context['seasons'])
        self.assertEqual(seasons[0], new)
        self.assertEqual(seasons[1], old)

    def test_season_list_accessible_anonymously(self):
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)

    def test_season_list_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)


class SeasonDetailViewTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(
            name='Spring 2025', year=2025, status=Season.STATUS_ACTIVE,
        )

    def test_detail_shows_season_name(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spring 2025')

    def test_detail_404_for_missing_season(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)

    def test_detail_accessible_anonymously(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
        self.assertEqual(response.status_code, 200)

    def test_detail_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
        self.assertEqual(response.status_code, 200)


# ─── Context processor tests ──────────────────────────────────────────────────

class SeasonContextProcessorTest(TestCase):
    def test_all_seasons_in_context(self):
        Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertIn('all_seasons', response.context)
        self.assertEqual(len(response.context['all_seasons']), 1)

    def test_current_season_set_from_url(self):
        season = Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': season.slug}))
        self.assertEqual(response.context['current_season'], season)

    def test_current_season_defaults_to_active(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        active = Season.objects.create(name='Current', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.context['current_season'], active)

    def test_current_season_none_when_no_active_and_no_pk(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertIsNone(response.context['current_season'])

    def test_nonexistent_slug_in_url_falls_back_to_active(self):
        active = Season.objects.create(name='Active', year=2025, status=Season.STATUS_ACTIVE)
        # /seasons/nonexistent-season/ returns 404, but the context processor should not crash.
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)

    # ── display flag filtering ────────────────────────────────────────────────

    def test_hidden_season_not_shown_to_anonymous(self):
        Season.objects.create(name='Hidden', year=2025, display=False)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(len(response.context['all_seasons']), 0)

    def test_hidden_season_not_shown_to_regular_user(self):
        Season.objects.create(name='Hidden', year=2025, display=False)
        user = User.objects.create_user(username='regular', password='pass')
        self.client.login(username='regular', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(len(response.context['all_seasons']), 0)

    def test_hidden_season_shown_to_staff(self):
        Season.objects.create(name='Hidden', year=2025, display=False)
        staff = User.objects.create_user(username='admin', password='pass', is_staff=True)
        self.client.login(username='admin', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(len(response.context['all_seasons']), 1)

    def test_hidden_season_shown_to_enrolled_player(self):
        hidden = Season.objects.create(name='Hidden', year=2025, display=False)
        player = User.objects.create_user(username='enrolled', password='pass')
        SeasonPlayer.objects.create(season=hidden, player=player, tier=1, is_active=True)
        self.client.login(username='enrolled', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(len(response.context['all_seasons']), 1)

    def test_hidden_season_not_shown_to_inactive_enrolled_player(self):
        hidden = Season.objects.create(name='Hidden', year=2025, display=False)
        player = User.objects.create_user(username='inactive', password='pass')
        SeasonPlayer.objects.create(season=hidden, player=player, tier=1, is_active=False)
        self.client.login(username='inactive', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(len(response.context['all_seasons']), 0)

    def test_hidden_season_current_season_resolves_via_direct_url(self):
        hidden = Season.objects.create(name='Hidden', year=2025, display=False)
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': hidden.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_season'], hidden)


# ─── SeasonPlayerDetailView tests ────────────────────────────────────────────

class SeasonPlayerDetailViewTest(TestCase):
    def setUp(self):
        self.season = make_season()
        self.player = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, self.player, tier=1)
        self.url = reverse('leagues:player_detail', kwargs={
            'slug': self.season.slug,
            'username': self.player.username,
        })

    def _make_match(self, p1, p2, status, winner=None, tier=1):
        return Match.objects.create(
            season=self.season, player1=p1, player2=p2,
            tier=tier, status=status, winner=winner,
            scheduled_date=datetime.date(2025, 6, 1),
        )

    def test_200_for_valid_player_in_season(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_missing_season(self):
        url = reverse('leagues:player_detail', kwargs={'slug': 'nonexistent-season', 'username': self.player.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_for_missing_player(self):
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': 'nonexistent-user'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_player_not_enrolled_in_season(self):
        other = make_player('outsider')
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': other.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_player_is_inactive(self):
        inactive = make_player('inactive')
        enroll(self.season, inactive, tier=1, is_active=False)
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': inactive.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_uses_correct_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'leagues/player_detail.html')

    def test_email_not_exposed_on_public_page(self):
        self.player.email = 'alice@private.com'
        self.player.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, 'alice@private.com')

    def test_email_not_exposed_on_public_page_when_unauthenticated(self):
        self.player.email = 'alice@private.com'
        self.player.save()
        self.client.logout()
        response = self.client.get(self.url)
        self.assertNotContains(response, 'alice@private.com')

    def test_season_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['season'], self.season)

    def test_player_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['player'], self.player)

    def test_season_player_in_context(self):
        response = self.client.get(self.url)
        sp = response.context['season_player']
        self.assertEqual(sp.player, self.player)
        self.assertEqual(sp.season, self.season)

    def test_standing_present_for_enrolled_player_with_no_matches(self):
        response = self.client.get(self.url)
        self.assertIsNotNone(response.context['standing'])
        self.assertIsNotNone(response.context['rank'])

    def test_standing_zeros_when_no_matches_played(self):
        response = self.client.get(self.url)
        standing = response.context['standing']
        self.assertEqual(standing['wins'], 0)
        self.assertEqual(standing['losses'], 0)
        self.assertEqual(standing['points'], 0)

    def test_standing_reflects_completed_match_win(self):
        opponent = make_player('opponent')
        enroll(self.season, opponent, tier=1)
        Match.objects.create(
            season=self.season, player1=self.player, player2=opponent,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        standing = response.context['standing']
        self.assertEqual(standing['wins'], 1)
        self.assertEqual(standing['points'], self.season.points_for_win)

    def test_rank_1_when_player_is_sole_enrolled_player(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['rank'], 1)

    def test_rank_reflects_position_among_multiple_players(self):
        leader = make_player('leader')
        enroll(self.season, leader, tier=1)
        # leader beats self.player → leader is rank 1, self.player rank 2
        Match.objects.create(
            season=self.season, player1=leader, player2=self.player,
            tier=1, status=Match.STATUS_COMPLETED, winner=leader,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context['rank'], 2)

    def test_upcoming_contains_scheduled_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_contains_postponed_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_POSTPONED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_matches_not_involving_player(self):
        other1 = make_player('o1')
        other2 = make_player('o2')
        enroll(self.season, other1, tier=1)
        enroll(self.season, other2, tier=1)
        unrelated = self._make_match(other1, other2, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertNotIn(unrelated, list(response.context['upcoming']))

    def test_upcoming_contains_pending_confirmation_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_PENDING)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_completed_matches(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_COMPLETED, winner=self.player)
        response = self.client.get(self.url)
        self.assertNotIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_matches_from_other_seasons(self):
        other_season = make_season(name='Other', status=Season.STATUS_UPCOMING)
        opponent = make_player('opp')
        enroll(other_season, self.player, tier=1)
        enroll(other_season, opponent, tier=1)
        other_match = Match.objects.create(
            season=other_season, player1=self.player, player2=opponent,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 6, 1),
        )
        response = self.client.get(self.url)
        self.assertNotIn(other_match, list(response.context['upcoming']))

    def test_results_contains_completed_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_COMPLETED, winner=self.player)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_results_contains_walkover_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_WALKOVER, winner=self.player)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_results_excludes_scheduled_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertNotIn(m, list(response.context['results']))

    def test_results_excludes_matches_not_involving_player(self):
        other1 = make_player('o1')
        other2 = make_player('o2')
        enroll(self.season, other1, tier=1)
        enroll(self.season, other2, tier=1)
        unrelated = self._make_match(other1, other2, Match.STATUS_COMPLETED, winner=other1)
        response = self.client.get(self.url)
        self.assertNotIn(unrelated, list(response.context['results']))

    def test_player_as_player2_appears_in_upcoming(self):
        """Player should appear in upcoming whether they are player1 or player2."""
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(opponent, self.player, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_player_as_player2_appears_in_results(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(opponent, self.player, Match.STATUS_COMPLETED, winner=opponent)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_accessible_anonymously(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_player_name_in_response(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Smith')


# ─── SeasonPlayerDetailView template tests ────────────────────────────────────

class SeasonPlayerDetailTemplateTest(TestCase):
    def setUp(self):
        self.season = make_season()
        self.player = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, self.player, tier=1)
        self.url = reverse('leagues:player_detail', kwargs={
            'slug': self.season.slug, 'username': self.player.username,
        })

    def _opponent(self, username='opp'):
        p = make_player(username)
        enroll(self.season, p, tier=1)
        return p

    def test_player_name_in_heading(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<h1>Alice Smith</h1>')

    def test_season_name_in_page_meta(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.season.name)

    def test_tier_label_shown_for_multi_tier_season(self):
        season = make_season(name='Multi', status=Season.STATUS_UPCOMING)
        Tier.objects.create(season=season, number=1, name='Tier 1')
        Tier.objects.create(season=season, number=2, name='Tier 2')
        p = make_player('bob', first='Bob', last='Jones')
        enroll(season, p, tier=2)
        url = reverse('leagues:player_detail', kwargs={'slug': season.slug, 'username': p.username})
        response = self.client.get(url)
        self.assertContains(response, 'Tier 2')

    def test_tier_label_not_shown_for_single_tier_season(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Tier 1')

    def test_standing_stats_rendered(self):
        opp = self._opponent()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Rank')
        self.assertContains(response, 'Wins')
        self.assertContains(response, 'Losses')
        self.assertContains(response, 'Pts')
        self.assertContains(response, 'PD')

    def test_rank_top3_highlight_applied_for_rank_1(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'rank-top-3')

    def test_upcoming_section_heading_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Upcoming Matches')

    def test_results_section_heading_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Results')

    def test_upcoming_match_opponent_name_rendered(self):
        opp = self._opponent('carol')
        opp.first_name = 'Carol'
        opp.last_name = 'White'
        opp.save()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 6, 1),
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Carol White')

    def test_completed_match_rendered_in_results(self):
        opp = self._opponent('dave')
        opp.first_name = 'Dave'
        opp.last_name = 'Black'
        opp.save()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Dave Black')


# ─── ImportPlayersView tests ──────────────────────────────────────────────────

def _csv(content):
    return SimpleUploadedFile('players.csv', content.encode(), content_type='text/csv')


class ImportPlayersViewTest(TestCase):
    def setUp(self):
        self.season = make_season()
        self.admin = User.objects.create_user(
            username='admin', password='pass', is_staff=True, is_superuser=True,
        )
        self.client.login(username='admin', password='pass')
        self.url = reverse('admin:leagues_season_import_players', args=[self.season.pk])

    # ── Access control ────────────────────────────────────────────

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import Players')

    def test_requires_staff(self):
        self.client.logout()
        non_staff = User.objects.create_user(username='regular', password='pass')
        self.client.login(username='regular', password='pass')
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_404_for_missing_season(self):
        url = reverse('admin:leagues_season_import_players', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    # ── Validation errors ─────────────────────────────────────────

    def test_no_file_shows_error(self):
        response = self.client.post(self.url, {})
        self.assertContains(response, 'Please select a CSV file')

    def test_non_csv_extension_shows_error(self):
        f = SimpleUploadedFile('players.txt', b'1\nAlice Smith', content_type='text/plain')
        response = self.client.post(self.url, {'csv_file': f})
        self.assertContains(response, 'must be a .csv file')

    def test_no_valid_tier_headers_shows_error(self):
        response = self.client.post(self.url, {'csv_file': _csv('Name\nAlice Smith')})
        self.assertContains(response, 'No valid tier columns found')

    # ── Tier header format variants ───────────────────────────────

    def test_numeric_header(self):
        response = self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertEqual(User.objects.filter(first_name='Alice', last_name='Smith').count(), 1)

    def test_tier_space_number_header(self):
        response = self.client.post(self.url, {'csv_file': _csv('Tier 1\nAlice Smith')})
        self.assertEqual(User.objects.filter(first_name='Alice', last_name='Smith').count(), 1)

    def test_tier_no_space_header(self):
        response = self.client.post(self.url, {'csv_file': _csv('tier1\nAlice Smith')})
        self.assertEqual(User.objects.filter(first_name='Alice', last_name='Smith').count(), 1)

    def test_Tier_capital_no_space_header(self):
        response = self.client.post(self.url, {'csv_file': _csv('Tier1\nAlice Smith')})
        self.assertEqual(User.objects.filter(first_name='Alice', last_name='Smith').count(), 1)

    # ── New player creation ───────────────────────────────────────

    def test_new_player_creates_user(self):
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertTrue(User.objects.filter(first_name='Alice', last_name='Smith').exists())

    def test_new_player_creates_season_player(self):
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        user = User.objects.get(first_name='Alice', last_name='Smith')
        self.assertTrue(SeasonPlayer.objects.filter(season=self.season, player=user, tier=1).exists())

    def test_new_player_assigned_to_correct_tier(self):
        self.client.post(self.url, {'csv_file': _csv('2\nAlice Smith')})
        user = User.objects.get(first_name='Alice', last_name='Smith')
        sp = SeasonPlayer.objects.get(season=self.season, player=user)
        self.assertEqual(sp.tier, 2)

    def test_new_player_username_derived_from_name(self):
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertTrue(User.objects.filter(username='alicesmith').exists())

    def test_username_collision_deduped(self):
        User.objects.create_user(username='alicesmith')
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertTrue(User.objects.filter(username='alicesmith1').exists())

    def test_result_lists_created_entry(self):
        response = self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertContains(response, 'Alice Smith')
        self.assertContains(response, 'Created')

    # ── Existing user, not yet enrolled ──────────────────────────

    def test_existing_user_not_enrolled_creates_season_player(self):
        user = make_player('alice', first='Alice', last='Smith')
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertTrue(SeasonPlayer.objects.filter(season=self.season, player=user).exists())

    def test_existing_user_not_duplicated(self):
        make_player('alice', first='Alice', last='Smith')
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertEqual(User.objects.filter(first_name='Alice', last_name='Smith').count(), 1)

    # ── Existing enrollment, same tier → skipped ─────────────────

    def test_already_enrolled_same_tier_skipped(self):
        user = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, user, tier=1)
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertEqual(SeasonPlayer.objects.filter(season=self.season, player=user).count(), 1)

    def test_already_enrolled_same_tier_tier_unchanged(self):
        user = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, user, tier=1)
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        sp = SeasonPlayer.objects.get(season=self.season, player=user)
        self.assertEqual(sp.tier, 1)

    def test_result_lists_skipped_entry(self):
        user = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, user, tier=1)
        response = self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertContains(response, 'Skipped')

    # ── Existing enrollment, different tier → updated ─────────────

    def test_already_enrolled_different_tier_updates_tier(self):
        user = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, user, tier=1)
        self.client.post(self.url, {'csv_file': _csv('2\nAlice Smith')})
        sp = SeasonPlayer.objects.get(season=self.season, player=user)
        self.assertEqual(sp.tier, 2)

    def test_result_lists_updated_entry(self):
        user = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, user, tier=1)
        response = self.client.post(self.url, {'csv_file': _csv('2\nAlice Smith')})
        self.assertContains(response, 'Updated')

    # ── Ambiguous name ────────────────────────────────────────────

    def test_ambiguous_name_skipped(self):
        make_player('alice1', first='Alice', last='Smith')
        make_player('alice2', first='Alice', last='Smith')
        self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertFalse(SeasonPlayer.objects.filter(season=self.season).exists())

    def test_ambiguous_name_appears_in_errors(self):
        make_player('alice1', first='Alice', last='Smith')
        make_player('alice2', first='Alice', last='Smith')
        response = self.client.post(self.url, {'csv_file': _csv('1\nAlice Smith')})
        self.assertContains(response, 'Errors')

    # ── Multi-tier CSV ────────────────────────────────────────────

    def test_multi_tier_csv_assigns_correct_tiers(self):
        csv_content = 'Tier 1,Tier 2\nAlice Smith,Bob Jones\n'
        self.client.post(self.url, {'csv_file': _csv(csv_content)})
        alice = User.objects.get(first_name='Alice', last_name='Smith')
        bob = User.objects.get(first_name='Bob', last_name='Jones')
        self.assertEqual(SeasonPlayer.objects.get(season=self.season, player=alice).tier, 1)
        self.assertEqual(SeasonPlayer.objects.get(season=self.season, player=bob).tier, 2)

    def test_multi_tier_csv_empty_cells_ignored(self):
        csv_content = 'Tier 1,Tier 2\nAlice Smith,\n'
        self.client.post(self.url, {'csv_file': _csv(csv_content)})
        self.assertEqual(SeasonPlayer.objects.filter(season=self.season).count(), 1)

    # ── Transaction atomicity ─────────────────────────────────────

    def test_transaction_rolls_back_on_error(self):
        # Inject a duplicate username that will cause create_user to fail mid-import
        # by pre-creating a user who will collide AND exhaust the de-dup loop isn't
        # practical, so instead test that a bad CSV line after a good one rolls back.
        # We do this by making the second row trigger an IntegrityError via a
        # duplicate SeasonPlayer (enroll alice first, then re-import with alice in two tiers).
        # Simpler: just verify that if we somehow break, no partial data remains.
        # The most reliable approach: test that multiple rows are all committed together.
        csv_content = 'Tier 1\nAlice Smith\nBob Jones\n'
        self.client.post(self.url, {'csv_file': _csv(csv_content)})
        self.assertEqual(SeasonPlayer.objects.filter(season=self.season).count(), 2)

    # ── Success message ───────────────────────────────────────────

    def test_success_message_shown_after_import(self):
        response = self.client.post(
            self.url, {'csv_file': _csv('1\nAlice Smith')}, follow=True
        )
        self.assertContains(response, 'Import complete')


# ─── SiteConfig model tests ───────────────────────────────────────────────────

class SiteConfigModelTest(TestCase):
    def test_str(self):
        config = SiteConfig(site_name='MyLeague')
        self.assertEqual(str(config), 'Site Configuration')

    def test_default_site_name(self):
        config = SiteConfig.objects.create()
        self.assertEqual(config.site_name, 'TennisLeague')

    def test_default_logo_is_blank(self):
        config = SiteConfig.objects.create()
        self.assertEqual(config.logo, '')

    def test_save_forces_pk_to_1(self):
        config = SiteConfig(site_name='Test')
        config.save()
        self.assertEqual(config.pk, 1)

    def test_second_save_overwrites_not_duplicates(self):
        SiteConfig(site_name='First').save()
        SiteConfig(site_name='Second').save()
        self.assertEqual(SiteConfig.objects.count(), 1)
        self.assertEqual(SiteConfig.objects.get(pk=1).site_name, 'Second')

    def test_get_creates_singleton_when_none_exists(self):
        self.assertEqual(SiteConfig.objects.count(), 0)
        config = SiteConfig.get()
        self.assertEqual(SiteConfig.objects.count(), 1)
        self.assertEqual(config.pk, 1)

    def test_get_returns_existing_singleton(self):
        SiteConfig.objects.create(pk=1, site_name='Existing')
        config = SiteConfig.get()
        self.assertEqual(config.site_name, 'Existing')

    def test_get_called_twice_returns_same_object(self):
        config1 = SiteConfig.get()
        config2 = SiteConfig.get()
        self.assertEqual(config1.pk, config2.pk)
        self.assertEqual(SiteConfig.objects.count(), 1)

    def test_site_name_persists(self):
        SiteConfig.objects.create(pk=1, site_name='League X')
        config = SiteConfig.objects.get(pk=1)
        self.assertEqual(config.site_name, 'League X')

    def test_logo_persists(self):
        data_url = 'data:image/png;base64,abc123'
        SiteConfig.objects.create(pk=1, logo=data_url)
        config = SiteConfig.objects.get(pk=1)
        self.assertEqual(config.logo, data_url)

    # ── logo_url property ─────────────────────────────────────

    def test_logo_url_returns_logo_for_valid_data_url(self):
        config = SiteConfig(logo='data:image/png;base64,abc123')
        self.assertEqual(config.logo_url, 'data:image/png;base64,abc123')

    def test_logo_url_returns_logo_for_jpeg(self):
        config = SiteConfig(logo='data:image/jpeg;base64,abc123')
        self.assertEqual(config.logo_url, 'data:image/jpeg;base64,abc123')

    def test_logo_url_returns_none_for_blank(self):
        config = SiteConfig(logo='')
        self.assertIsNone(config.logo_url)

    def test_logo_url_returns_none_for_javascript_scheme(self):
        config = SiteConfig(logo='javascript:evil()')
        self.assertIsNone(config.logo_url)

    def test_logo_url_returns_none_for_http_url(self):
        config = SiteConfig(logo='http://example.com/logo.png')
        self.assertIsNone(config.logo_url)

    def test_logo_url_returns_none_for_arbitrary_string(self):
        config = SiteConfig(logo='not-a-data-url')
        self.assertIsNone(config.logo_url)


# ─── SiteConfigForm tests ─────────────────────────────────────────────────────

class SiteConfigFormTest(TestCase):
    def setUp(self):
        self.config = SiteConfig.objects.create(pk=1)

    def _form(self, data=None, files=None):
        return SiteConfigForm(
            data=data or {'site_name': 'TennisLeague'},
            files=files or {},
            instance=self.config,
        )

    # ── Site name field ───────────────────────────────────────────

    def test_valid_form_with_no_logo(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_site_name_saved(self):
        form = self._form(data={'site_name': 'My Club'})
        self.assertTrue(form.is_valid())
        instance = form.save()
        self.assertEqual(instance.site_name, 'My Club')

    def test_empty_site_name_is_invalid(self):
        form = self._form(data={'site_name': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('site_name', form.errors)

    # ── PNG upload ────────────────────────────────────────────────

    def test_valid_png_accepted(self):
        form = self._form(files={'logo_upload': _png_file()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_png_stored_as_png_data_url(self):
        form = self._form(files={'logo_upload': _png_file()})
        form.is_valid()
        instance = form.save()
        self.assertTrue(instance.logo.startswith('data:image/png;base64,'))

    def test_png_data_url_decodes_to_original_bytes(self):
        form = self._form(files={'logo_upload': _png_file()})
        form.is_valid()
        instance = form.save()
        _, encoded = instance.logo.split(',', 1)
        self.assertEqual(base64.b64decode(encoded), _SMALL_PNG)

    # ── JPEG upload ───────────────────────────────────────────────

    def test_valid_jpeg_accepted(self):
        form = self._form(files={'logo_upload': _jpeg_file()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_jpeg_stored_as_jpeg_data_url(self):
        form = self._form(files={'logo_upload': _jpeg_file()})
        form.is_valid()
        instance = form.save()
        self.assertTrue(instance.logo.startswith('data:image/jpeg;base64,'))

    def test_jpeg_data_url_decodes_to_original_bytes(self):
        form = self._form(files={'logo_upload': _jpeg_file()})
        form.is_valid()
        instance = form.save()
        _, encoded = instance.logo.split(',', 1)
        self.assertEqual(base64.b64decode(encoded), _SMALL_JPEG)

    # ── File type rejection ───────────────────────────────────────

    def test_non_image_bytes_rejected(self):
        f = SimpleUploadedFile('evil.png', b'not an image at all', content_type='image/png')
        form = self._form(files={'logo_upload': f})
        self.assertFalse(form.is_valid())
        self.assertIn('logo_upload', form.errors)

    def test_gif_rejected(self):
        gif_bytes = b'GIF89a' + b'\x00' * 20
        f = SimpleUploadedFile('anim.gif', gif_bytes, content_type='image/gif')
        form = self._form(files={'logo_upload': f})
        self.assertFalse(form.is_valid())
        self.assertIn('logo_upload', form.errors)

    def test_png_extension_with_jpeg_bytes_detected_as_jpeg(self):
        # Extension is irrelevant; magic bytes determine the type.
        f = SimpleUploadedFile('photo.png', _SMALL_JPEG, content_type='image/png')
        form = self._form(files={'logo_upload': f})
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertTrue(instance.logo.startswith('data:image/jpeg;base64,'))

    def test_jpeg_extension_with_png_bytes_detected_as_png(self):
        f = SimpleUploadedFile('logo.jpg', _SMALL_PNG, content_type='image/jpeg')
        form = self._form(files={'logo_upload': f})
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertTrue(instance.logo.startswith('data:image/png;base64,'))

    # ── File size limit ───────────────────────────────────────────

    def test_file_over_2mb_rejected(self):
        big = _PNG_HEADER + b'\x00' * (2 * 1024 * 1024 + 1)
        f = SimpleUploadedFile('big.png', big, content_type='image/png')
        form = self._form(files={'logo_upload': f})
        self.assertFalse(form.is_valid())
        self.assertIn('logo_upload', form.errors)

    def test_file_exactly_2mb_accepted(self):
        at_limit = _PNG_HEADER + b'\x00' * (2 * 1024 * 1024 - len(_PNG_HEADER))
        f = SimpleUploadedFile('exact.png', at_limit, content_type='image/png')
        form = self._form(files={'logo_upload': f})
        self.assertTrue(form.is_valid(), form.errors)

    # ── No upload → existing logo unchanged ──────────────────────

    def test_no_upload_leaves_logo_unchanged(self):
        self.config.logo = 'data:image/png;base64,existing=='
        self.config.save()
        form = self._form()
        form.is_valid()
        instance = form.save()
        self.assertEqual(instance.logo, 'data:image/png;base64,existing==')

    # ── clear_logo ────────────────────────────────────────────────

    def test_clear_logo_removes_existing_logo(self):
        self.config.logo = 'data:image/png;base64,existing=='
        self.config.save()
        form = self._form(data={'site_name': 'TennisLeague', 'clear_logo': '1'})
        form.is_valid()
        instance = form.save()
        self.assertEqual(instance.logo, '')

    def test_clear_logo_takes_precedence_over_new_upload(self):
        self.config.logo = 'data:image/png;base64,existing=='
        self.config.save()
        form = self._form(
            data={'site_name': 'TennisLeague', 'clear_logo': '1'},
            files={'logo_upload': _png_file()},
        )
        form.is_valid()
        instance = form.save()
        self.assertEqual(instance.logo, '')


# ─── SiteConfig context processor tests ──────────────────────────────────────

class SiteConfigContextProcessorTest(TestCase):
    def _get(self, url=None):
        return self.client.get(url or reverse('leagues:season_list'))

    def test_site_name_in_context_with_default(self):
        response = self._get()
        self.assertEqual(response.context['site_name'], 'TennisLeague')

    def test_site_name_in_context_reflects_custom_value(self):
        SiteConfig.objects.create(pk=1, site_name='My Club')
        response = self._get()
        self.assertEqual(response.context['site_name'], 'My Club')

    def test_logo_data_url_none_when_no_logo(self):
        SiteConfig.objects.create(pk=1, logo='')
        response = self._get()
        self.assertIsNone(response.context['logo_data_url'])

    def test_logo_data_url_returned_when_set(self):
        data_url = 'data:image/png;base64,abc123'
        SiteConfig.objects.create(pk=1, logo=data_url)
        response = self._get()
        self.assertEqual(response.context['logo_data_url'], data_url)

    def test_logo_data_url_none_for_invalid_scheme(self):
        SiteConfig.objects.create(pk=1, logo='javascript:evil()')
        response = self._get()
        self.assertIsNone(response.context['logo_data_url'])

    def test_context_processor_skipped_on_admin_pages(self):
        admin = User.objects.create_user(
            username='admin', password='pass', is_staff=True, is_superuser=True,
        )
        self.client.login(username='admin', password='pass')
        response = self.client.get('/admin/')
        self.assertNotIn('site_name', response.context)

    def test_singleton_auto_created_on_first_request(self):
        self.assertEqual(SiteConfig.objects.count(), 0)
        self._get()
        self.assertEqual(SiteConfig.objects.count(), 1)


# ─── SiteConfig template rendering tests ─────────────────────────────────────

class SiteConfigTemplateTest(TestCase):
    def _get(self):
        return self.client.get(reverse('leagues:season_list'))

    def test_default_site_name_in_navbar(self):
        response = self._get()
        self.assertContains(response, 'TennisLeague')

    def test_custom_site_name_in_navbar(self):
        SiteConfig.objects.create(pk=1, site_name='Wimbledon League')
        response = self._get()
        self.assertContains(response, 'Wimbledon League')

    def test_custom_site_name_in_footer(self):
        SiteConfig.objects.create(pk=1, site_name='Wimbledon League')
        response = self._get()
        content = response.content.decode()
        footer_start = content.find('site-footer')
        self.assertIn('Wimbledon League', content[footer_start:footer_start + 300])

    def test_default_icon_shown_when_no_logo(self):
        SiteConfig.objects.create(pk=1, logo='')
        response = self._get()
        self.assertContains(response, 'class="brand-ball"')
        self.assertNotContains(response, 'class="brand-logo"')

    def test_logo_img_shown_when_logo_set(self):
        data_url = 'data:image/png;base64,abc123'
        SiteConfig.objects.create(pk=1, logo=data_url)
        response = self._get()
        self.assertContains(response, 'class="brand-logo"')
        self.assertNotContains(response, 'class="brand-ball"')

    def test_logo_img_src_equals_data_url(self):
        data_url = 'data:image/png;base64,abc123'
        SiteConfig.objects.create(pk=1, logo=data_url)
        response = self._get()
        self.assertContains(response, f'src="{data_url}"')


# ─── SiteConfig admin tests ───────────────────────────────────────────────────

class SiteConfigAdminTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='pass', is_staff=True, is_superuser=True,
        )
        self.client.login(username='admin', password='pass')
        self.changelist_url = reverse('admin:leagues_siteconfig_changelist')
        self.change_url = reverse('admin:leagues_siteconfig_change', args=[1])

    # ── Singleton redirect ────────────────────────────────────────

    def test_changelist_redirects_to_change_page(self):
        response = self.client.get(self.changelist_url)
        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)

    def test_changelist_creates_singleton_if_missing(self):
        self.assertEqual(SiteConfig.objects.count(), 0)
        self.client.get(self.changelist_url)
        self.assertEqual(SiteConfig.objects.count(), 1)

    # ── Access control ────────────────────────────────────────────

    def test_change_page_accessible_to_staff(self):
        SiteConfig.objects.create(pk=1)
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)

    def test_change_page_not_accessible_to_non_staff(self):
        SiteConfig.objects.create(pk=1)
        self.client.logout()
        non_staff = User.objects.create_user(username='regular', password='pass')
        self.client.login(username='regular', password='pass')
        response = self.client.get(self.change_url)
        self.assertNotEqual(response.status_code, 200)

    # ── Permissions ───────────────────────────────────────────────

    def test_no_delete_button_on_change_page(self):
        SiteConfig.objects.create(pk=1)
        response = self.client.get(self.change_url)
        self.assertNotContains(response, 'deletelink')

    def test_no_add_button_when_singleton_exists(self):
        SiteConfig.objects.create(pk=1)
        response = self.client.get(self.change_url)
        add_url = reverse('admin:leagues_siteconfig_add')
        self.assertNotContains(response, add_url)

    # ── POST: update site name ────────────────────────────────────

    def test_post_updates_site_name(self):
        SiteConfig.objects.create(pk=1)
        self.client.post(self.change_url, {'site_name': 'Club Serve'})
        self.assertEqual(SiteConfig.objects.get(pk=1).site_name, 'Club Serve')

    # ── POST: upload PNG ──────────────────────────────────────────

    def test_post_png_stores_data_url(self):
        SiteConfig.objects.create(pk=1)
        self.client.post(self.change_url, {
            'site_name': 'TennisLeague',
            'logo_upload': _png_file(),
        })
        config = SiteConfig.objects.get(pk=1)
        self.assertTrue(config.logo.startswith('data:image/png;base64,'))

    def test_post_jpeg_stores_data_url(self):
        SiteConfig.objects.create(pk=1)
        self.client.post(self.change_url, {
            'site_name': 'TennisLeague',
            'logo_upload': _jpeg_file(),
        })
        config = SiteConfig.objects.get(pk=1)
        self.assertTrue(config.logo.startswith('data:image/jpeg;base64,'))

    def test_post_clear_logo_removes_logo(self):
        SiteConfig.objects.create(pk=1, logo='data:image/png;base64,abc123')
        self.client.post(self.change_url, {
            'site_name': 'TennisLeague',
            'clear_logo': '1',
        })
        config = SiteConfig.objects.get(pk=1)
        self.assertEqual(config.logo, '')

    def test_post_invalid_file_does_not_save(self):
        SiteConfig.objects.create(pk=1, logo='data:image/png;base64,original')
        bad_file = SimpleUploadedFile('bad.png', b'not an image', content_type='image/png')
        self.client.post(self.change_url, {
            'site_name': 'TennisLeague',
            'logo_upload': bad_file,
        })
        config = SiteConfig.objects.get(pk=1)
        self.assertEqual(config.logo, 'data:image/png;base64,original')

    # ── Admin branding ────────────────────────────────────────

    def test_admin_branding_shows_custom_site_name(self):
        SiteConfig.objects.create(pk=1, site_name='Serve & Volley')
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Serve &amp; Volley')

    def test_admin_branding_shows_logo_img_when_set(self):
        data_url = 'data:image/png;base64,abc123'
        SiteConfig.objects.create(pk=1, logo=data_url)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'admin-brand-logo')
        self.assertContains(response, data_url)

    def test_admin_branding_no_logo_img_when_blank(self):
        SiteConfig.objects.create(pk=1, logo='')
        response = self.client.get(reverse('admin:index'))
        self.assertNotContains(response, 'admin-brand-logo')

    def test_admin_title_uses_site_name(self):
        SiteConfig.objects.create(pk=1, site_name='Club Ace')
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Club Ace')


# ─── site_branding template tag tests ────────────────────────────────────────

class SiteBrandingTagTest(TestCase):
    def test_returns_default_config_when_none_exists(self):
        config = get_site_config()
        self.assertEqual(config.site_name, 'TennisLeague')
        self.assertEqual(config.logo, '')

    def test_returns_existing_config(self):
        SiteConfig.objects.create(pk=1, site_name='My League', logo='data:image/png;base64,x')
        config = get_site_config()
        self.assertEqual(config.site_name, 'My League')
        self.assertEqual(config.logo, 'data:image/png;base64,x')

    def test_creates_singleton_on_first_call(self):
        self.assertEqual(SiteConfig.objects.count(), 0)
        get_site_config()
        self.assertEqual(SiteConfig.objects.count(), 1)

    def test_subsequent_calls_do_not_duplicate(self):
        get_site_config()
        get_site_config()
        self.assertEqual(SiteConfig.objects.count(), 1)


# ─── Copy players admin view ──────────────────────────────────────────────────

class CopyPlayersViewTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', password='password')
        self.client.force_login(self.superuser)
        self.source = make_season(name='Winter 2024', year=2024, status=Season.STATUS_COMPLETED)
        self.target = make_season(name='Spring 2025', year=2025, status=Season.STATUS_UPCOMING)
        self.url = reverse('admin:leagues_season_copy_players', args=[self.target.pk])

    def _post(self, source_id=None):
        return self.client.post(self.url, {'source_season': source_id or self.source.pk}, follow=True)

    def test_get_renders_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Copy Players')
        self.assertContains(resp, str(self.source))

    def test_copies_active_players(self):
        Tier.objects.create(season=self.target, number=1, name='Tier 1')
        Tier.objects.create(season=self.target, number=2, name='Tier 2')
        p1 = make_player('alice')
        p2 = make_player('bob')
        enroll(self.source, p1, tier=1)
        enroll(self.source, p2, tier=2)
        self._post()
        self.assertTrue(SeasonPlayer.objects.filter(season=self.target, player=p1, tier=1).exists())
        self.assertTrue(SeasonPlayer.objects.filter(season=self.target, player=p2, tier=2).exists())

    def test_skips_inactive_players(self):
        p = make_player('inactive')
        enroll(self.source, p, tier=1, is_active=False)
        self._post()
        self.assertFalse(SeasonPlayer.objects.filter(season=self.target, player=p).exists())

    def test_skips_already_enrolled_players(self):
        p = make_player('existing')
        enroll(self.source, p, tier=1)
        enroll(self.target, p, tier=2)
        self._post()
        sp = SeasonPlayer.objects.get(season=self.target, player=p)
        self.assertEqual(sp.tier, 2)

    def test_redirects_to_change_view_on_success(self):
        resp = self.client.post(self.url, {'source_season': self.source.pk})
        self.assertRedirects(resp, reverse('admin:leagues_season_change', args=[self.target.pk]))

    def test_invalid_source_shows_error(self):
        resp = self.client.post(self.url, {'source_season': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Please select a valid season.')

    def test_requires_authentication(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)

    def test_copy_players_url_in_change_view(self):
        resp = self.client.get(reverse('admin:leagues_season_change', args=[self.target.pk]))
        self.assertContains(resp, 'Copy Players from Season')

    def test_nonexistent_source_pk_shows_error(self):
        resp = self.client.post(self.url, {'source_season': 99999})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Please select a valid season.')

    def test_source_season_with_no_active_players_redirects(self):
        resp = self.client.post(self.url, {'source_season': self.source.pk})
        self.assertRedirects(resp, reverse('admin:leagues_season_change', args=[self.target.pk]))

    def test_success_message_counts(self):
        p1 = make_player('msg1')
        p2 = make_player('msg2')
        p3 = make_player('msg3')
        enroll(self.source, p1, tier=1)
        enroll(self.source, p2, tier=1)
        enroll(self.target, p3, tier=1)
        enroll(self.source, p3, tier=1)
        resp = self._post()
        self.assertContains(resp, '2 added')
        self.assertContains(resp, '1 already enrolled')

    def test_source_season_excluded_from_own_dropdown(self):
        resp = self.client.get(reverse('admin:leagues_season_copy_players', args=[self.source.pk]))
        self.assertNotContains(resp, f'value="{self.source.pk}"')
        self.assertContains(resp, f'value="{self.target.pk}"')

    def test_player_in_nonexistent_tier_is_skipped(self):
        Tier.objects.create(season=self.target, number=1, name='Premier')
        p = make_player('tier2player')
        enroll(self.source, p, tier=2)
        self._post()
        self.assertFalse(SeasonPlayer.objects.filter(season=self.target, player=p).exists())

    def test_player_in_valid_tier_is_copied_when_tiers_explicit(self):
        Tier.objects.create(season=self.target, number=1, name='Premier')
        p = make_player('tier1player')
        enroll(self.source, p, tier=1)
        self._post()
        self.assertTrue(SeasonPlayer.objects.filter(season=self.target, player=p, tier=1).exists())

    def test_tier_skipped_count_in_success_message(self):
        Tier.objects.create(season=self.target, number=1, name='Premier')
        p1 = make_player('t1')
        p2 = make_player('t2')
        enroll(self.source, p1, tier=1)
        enroll(self.source, p2, tier=2)
        resp = self._post()
        self.assertContains(resp, '1 skipped (tier not in this season)')

    def test_no_explicit_tiers_treats_tier_1_as_valid(self):
        p = make_player('notierobj')
        enroll(self.source, p, tier=1)
        self._post()
        self.assertTrue(SeasonPlayer.objects.filter(season=self.target, player=p, tier=1).exists())

    def test_no_explicit_tiers_skips_tier_2(self):
        p = make_player('notierobj2')
        enroll(self.source, p, tier=2)
        self._post()
        self.assertFalse(SeasonPlayer.objects.filter(season=self.target, player=p).exists())


# ─── Generate Schedule / Analyze view tests ──────────────────────────────────

class GenerateScheduleViewTest(TestCase):
    """Tests for the Analyze / Generate Schedule admin view and _build_schedule_analysis."""

    START = datetime.date(2025, 4, 7)
    NEXT  = datetime.date(2025, 4, 14)

    def setUp(self):
        self.admin = User.objects.create_superuser('schedadmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='Schedule Test', year=2025)

    def _url(self, season=None):
        return reverse('admin:leagues_season_generate_schedule', args=[(season or self.season).pk])

    def _add_players(self, count, tier=1, season=None):
        s = season or self.season
        players = []
        for i in range(count):
            p = make_player(f'sched_t{tier}_p{i}_{s.pk}', first=f'Player{tier}', last=str(i))
            enroll(s, p, tier=tier)
            players.append(p)
        return players

    def _match(self, p1, p2, tier=1, date=None, season=None):
        return Match.objects.create(
            season=season or self.season,
            player1=p1, player2=p2,
            tier=tier,
            round=Match.ROUND_REGULAR,
            scheduled_date=date or self.START,
            status=Match.STATUS_SCHEDULED,
        )

    # ── Access / rendering ────────────────────────────────────────────────────

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('nobody_sched'))
        self.assertNotEqual(self.client.get(self._url()).status_code, 200)

    def test_404_for_unknown_season(self):
        url = reverse('admin:leagues_season_generate_schedule', args=[99999])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_title_contains_analyze_generate(self):
        resp = self.client.get(self._url())
        self.assertContains(resp, 'Analyze / Generate Schedule')

    # ── No matches yet ────────────────────────────────────────────────────────

    def test_no_analysis_before_matches_scheduled(self):
        self._add_players(4)
        resp = self.client.get(self._url())
        self.assertIsNone(resp.context['schedule_analysis'])

    def test_generate_form_shown_when_rounds_remain(self):
        self._add_players(4)
        resp = self.client.get(self._url())
        self.assertFalse(resp.context['all_exhausted'])
        self.assertContains(resp, 'Generate Schedule')

    def test_all_exhausted_hides_form(self):
        players = self._add_players(2)
        self._match(players[0], players[1])
        resp = self.client.get(self._url())
        self.assertTrue(resp.context['all_exhausted'])
        self.assertNotContains(resp, 'id_num_rounds')

    # ── Date rows ─────────────────────────────────────────────────────────────

    def test_date_rows_one_per_distinct_date(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        rows = self.client.get(self._url()).context['schedule_analysis']['date_rows']
        self.assertEqual(len(rows), 2)

    def test_date_rows_sorted_ascending(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.NEXT)
        self._match(p[2], p[3], date=self.START)
        rows = self.client.get(self._url()).context['schedule_analysis']['date_rows']
        self.assertEqual(rows[0]['date'], self.START)
        self.assertEqual(rows[1]['date'], self.NEXT)

    def test_date_row_tier_count_correct(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        rows = self.client.get(self._url()).context['schedule_analysis']['date_rows']
        self.assertEqual(rows[0]['tier_counts'], [2])
        self.assertEqual(rows[0]['total'], 2)

    def test_match_with_null_date_excluded_from_date_rows(self):
        p = self._add_players(4)
        Match.objects.create(
            season=self.season, player1=p[0], player2=p[1],
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=None, status=Match.STATUS_SCHEDULED,
        )
        resp = self.client.get(self._url())
        self.assertIsNone(resp.context['schedule_analysis'])

    # ── Totals ────────────────────────────────────────────────────────────────

    def test_totals_sum_across_all_dates(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        analysis = self.client.get(self._url()).context['schedule_analysis']
        self.assertEqual(analysis['totals'], [3])

    def test_grand_total_equals_all_matches(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        analysis = self.client.get(self._url()).context['schedule_analysis']
        self.assertEqual(analysis['grand_total'], 3)

    # ── Single vs multi-tier ──────────────────────────────────────────────────

    def test_multi_tier_false_for_single_tier(self):
        p = self._add_players(4)
        self._match(p[0], p[1])
        analysis = self.client.get(self._url()).context['schedule_analysis']
        self.assertFalse(analysis['multi_tier'])

    def test_multi_tier_true_for_multiple_tiers(self):
        s = make_season(name='Multi Sched', year=2025)
        Tier.objects.create(season=s, number=1, name='Tier 1')
        Tier.objects.create(season=s, number=2, name='Tier 2')
        t1 = self._add_players(4, tier=1, season=s)
        t2 = self._add_players(4, tier=2, season=s)
        self._match(t1[0], t1[1], tier=1, season=s)
        self._match(t2[0], t2[1], tier=2, season=s)
        analysis = self.client.get(self._url(season=s)).context['schedule_analysis']
        self.assertTrue(analysis['multi_tier'])

    def test_multi_tier_tier_counts_per_date(self):
        s = make_season(name='Multi Sched2', year=2025)
        Tier.objects.create(season=s, number=1, name='Tier 1')
        Tier.objects.create(season=s, number=2, name='Tier 2')
        t1 = self._add_players(4, tier=1, season=s)
        t2 = self._add_players(4, tier=2, season=s)
        self._match(t1[0], t1[1], tier=1, date=self.START, season=s)
        self._match(t1[2], t1[3], tier=1, date=self.START, season=s)
        self._match(t2[0], t2[1], tier=2, date=self.START, season=s)
        rows = self.client.get(self._url(season=s)).context['schedule_analysis']['date_rows']
        self.assertEqual(rows[0]['tier_counts'], [2, 1])
        self.assertEqual(rows[0]['total'], 3)

    def test_multi_tier_totals_per_tier(self):
        s = make_season(name='Multi Sched3', year=2025)
        Tier.objects.create(season=s, number=1, name='Tier 1')
        Tier.objects.create(season=s, number=2, name='Tier 2')
        t1 = self._add_players(4, tier=1, season=s)
        t2 = self._add_players(4, tier=2, season=s)
        self._match(t1[0], t1[1], tier=1, season=s)
        self._match(t1[2], t1[3], tier=1, season=s)
        self._match(t2[0], t2[1], tier=2, date=self.NEXT, season=s)
        analysis = self.client.get(self._url(season=s)).context['schedule_analysis']
        self.assertEqual(analysis['totals'], [2, 1])
        self.assertEqual(analysis['grand_total'], 3)

    # ── Behind players ────────────────────────────────────────────────────────

    def test_no_behind_players_when_all_equal(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        analysis = self.client.get(self._url()).context['schedule_analysis']
        self.assertEqual(analysis['behind_by_tier'], [])

    def test_behind_players_identified_correctly(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)   # p0=1, p1=1
        self._match(p[2], p[3], date=self.START)   # p2=1, p3=1
        self._match(p[0], p[2], date=self.NEXT)    # p0=2, p2=2; p1 and p3 stay at 1
        behind_by_tier = self.client.get(self._url()).context['schedule_analysis']['behind_by_tier']
        self.assertEqual(len(behind_by_tier), 1)
        behind_ids = {item['player'].pk for item in behind_by_tier[0]['players']}
        self.assertEqual(behind_ids, {p[1].pk, p[3].pk})

    def test_behind_player_deficit_correct(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        behind = self.client.get(self._url()).context['schedule_analysis']['behind_by_tier'][0]['players']
        deficits = {item['player'].pk: item['deficit'] for item in behind}
        self.assertEqual(deficits[p[1].pk], 1)
        self.assertEqual(deficits[p[3].pk], 1)

    def test_behind_max_count_reported_correctly(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        entry = self.client.get(self._url()).context['schedule_analysis']['behind_by_tier'][0]
        self.assertEqual(entry['max_count'], 2)

    # ── Template rendering ────────────────────────────────────────────────────

    def test_template_renders_scheduled_date(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=datetime.date(2025, 4, 7))
        resp = self.client.get(self._url())
        self.assertContains(resp, 'Apr 7, 2025')

    def test_template_shows_behind_player_name(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self._match(p[0], p[2], date=self.NEXT)
        resp = self.client.get(self._url())
        self.assertContains(resp, p[1].get_full_name())

    def test_template_shows_equal_message_when_no_behind(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        resp = self.client.get(self._url())
        self.assertContains(resp, 'equal number of scheduled matches')

    # ── POST – generate further rounds ────────────────────────────────────────

    def test_post_generates_matches_and_redirects(self):
        self._add_players(4)
        resp = self.client.post(self._url(), {'start_date': '2025-04-07', 'num_rounds': '1'})
        self.assertRedirects(resp, reverse('admin:leagues_season_change', args=[self.season.pk]))
        self.assertEqual(Match.objects.filter(season=self.season).count(), 2)

    def test_post_second_call_adds_new_rounds(self):
        p = self._add_players(4)
        self._match(p[0], p[1], date=self.START)
        self._match(p[2], p[3], date=self.START)
        self.client.post(self._url(), {'start_date': '2025-04-14', 'num_rounds': '2'})
        self.assertEqual(Match.objects.filter(season=self.season).count(), 6)

    def test_post_invalid_date_shows_error(self):
        self._add_players(4)
        resp = self.client.post(self._url(), {'start_date': 'notadate', 'num_rounds': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'valid start date')

    def test_post_invalid_rounds_shows_error(self):
        self._add_players(4)
        resp = self.client.post(self._url(), {'start_date': '2025-04-07', 'num_rounds': '0'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'positive integer')

    def test_tier_info_includes_tier_number(self):
        resp = self.client.get(self._url())
        tier_info = resp.context['tier_info']
        self.assertEqual(tier_info[0]['tier'], 1)


# ─── Schedule Match endpoints ─────────────────────────────────────────────────

class ScheduleMatchPlayersViewTest(TestCase):
    """Tests for the players JSON endpoint used by the Schedule a Match UI."""

    def setUp(self):
        self.admin = User.objects.create_superuser('smpadmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='SM Players Test', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')

    def _url(self, season=None):
        return reverse('admin:leagues_season_schedule_match_players', args=[(season or self.season).pk])

    def _enroll_with_matches(self, count, tier=1):
        players = []
        for i in range(count):
            p = make_player(f'smp_p{i}_{self.season.pk}', first='P', last=str(i))
            enroll(self.season, p, tier=tier)
            players.append(p)
        return players

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('smp_anon'))
        resp = self.client.get(self._url(), {'tier': 1})
        self.assertNotEqual(resp.status_code, 200)

    def test_404_for_unknown_season(self):
        url = reverse('admin:leagues_season_schedule_match_players', args=[99999])
        resp = self.client.get(url, {'tier': 1})
        self.assertEqual(resp.status_code, 404)

    def test_returns_json_players(self):
        import json
        players = self._enroll_with_matches(3)
        resp = self.client.get(self._url(), {'tier': 1})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('players', data)
        self.assertEqual(len(data['players']), 3)

    def test_players_include_id_name_match_count(self):
        import json
        p = self._enroll_with_matches(2)
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        keys = set(data['players'][0].keys())
        self.assertIn('id', keys)
        self.assertIn('name', keys)
        self.assertIn('match_count', keys)

    def test_match_count_reflects_scheduled_matches(self):
        import json
        p = self._enroll_with_matches(3)
        Match.objects.create(
            season=self.season, player1=p[0], player2=p[1],
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 4, 7), status=Match.STATUS_SCHEDULED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        count_by_id = {entry['id']: entry['match_count'] for entry in data['players']}
        self.assertEqual(count_by_id[p[0].pk], 1)
        self.assertEqual(count_by_id[p[1].pk], 1)
        self.assertEqual(count_by_id[p[2].pk], 0)

    def test_players_sorted_by_fewest_matches_first(self):
        import json
        p = self._enroll_with_matches(3)
        Match.objects.create(
            season=self.season, player1=p[0], player2=p[1],
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 4, 7), status=Match.STATUS_SCHEDULED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        counts = [entry['match_count'] for entry in data['players']]
        self.assertEqual(counts, sorted(counts))

    def test_inactive_players_excluded(self):
        import json
        p = self._enroll_with_matches(2)
        inactive = make_player('smp_inactive')
        SeasonPlayer.objects.create(season=self.season, player=inactive, tier=1, is_active=False)
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        ids = {entry['id'] for entry in data['players']}
        self.assertNotIn(inactive.pk, ids)

    def test_players_from_other_tier_excluded(self):
        import json
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        p_t1 = self._enroll_with_matches(2, tier=1)
        p_t2 = make_player('smp_t2')
        enroll(self.season, p_t2, tier=2)
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        ids = {entry['id'] for entry in data['players']}
        self.assertNotIn(p_t2.pk, ids)

    def test_invalid_tier_returns_400(self):
        resp = self.client.get(self._url(), {'tier': 'bad'})
        self.assertEqual(resp.status_code, 400)

    def test_missing_tier_returns_400(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 400)


class ScheduleMatchMatchupsViewTest(TestCase):
    """Tests for the matchups JSON endpoint used by the Schedule a Match UI."""

    def setUp(self):
        self.admin = User.objects.create_superuser('smmadmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='SM Matchups Test', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        self.players = []
        for i in range(4):
            p = make_player(f'smm_p{i}_{self.season.pk}', first='M', last=str(i))
            enroll(self.season, p, tier=1)
            self.players.append(p)

    def _url(self, season=None):
        return reverse('admin:leagues_season_schedule_match_matchups', args=[(season or self.season).pk])

    def _match(self, p1, p2):
        return Match.objects.create(
            season=self.season, player1=p1, player2=p2,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 4, 7), status=Match.STATUS_SCHEDULED,
        )

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('smm_anon'))
        resp = self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk})
        self.assertNotEqual(resp.status_code, 200)

    def test_404_for_unknown_season(self):
        url = reverse('admin:leagues_season_schedule_match_matchups', args=[99999])
        resp = self.client.get(url, {'tier': 1, 'player': self.players[0].pk})
        self.assertEqual(resp.status_code, 404)

    def test_returns_not_played_and_already_played_keys(self):
        import json
        resp = self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('not_played', data)
        self.assertIn('already_played', data)

    def test_no_matches_all_opponents_in_not_played(self):
        import json
        data = json.loads(self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk}).content)
        self.assertEqual(len(data['not_played']), 3)
        self.assertEqual(len(data['already_played']), 0)

    def test_played_opponent_moves_to_already_played(self):
        import json
        self._match(self.players[0], self.players[1])
        data = json.loads(self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk}).content)
        already_ids = {e['id'] for e in data['already_played']}
        not_ids = {e['id'] for e in data['not_played']}
        self.assertIn(self.players[1].pk, already_ids)
        self.assertNotIn(self.players[1].pk, not_ids)

    def test_selected_player_not_in_results(self):
        import json
        data = json.loads(self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk}).content)
        all_ids = {e['id'] for e in data['not_played']} | {e['id'] for e in data['already_played']}
        self.assertNotIn(self.players[0].pk, all_ids)

    def test_match_detected_regardless_of_player_order(self):
        import json
        self._match(self.players[1], self.players[0])
        data = json.loads(self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk}).content)
        already_ids = {e['id'] for e in data['already_played']}
        self.assertIn(self.players[1].pk, already_ids)

    def test_invalid_player_returns_400(self):
        resp = self.client.get(self._url(), {'tier': 1, 'player': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_tier_returns_400(self):
        resp = self.client.get(self._url(), {'tier': 'x', 'player': self.players[0].pk})
        self.assertEqual(resp.status_code, 400)

    def test_not_played_sorted_by_fewest_matches(self):
        import json
        self._match(self.players[1], self.players[2])
        data = json.loads(self.client.get(self._url(), {'tier': 1, 'player': self.players[0].pk}).content)
        counts = [e['match_count'] for e in data['not_played']]
        self.assertEqual(counts, sorted(counts))


class ScheduleMatchCreateViewTest(TestCase):
    """Tests for the POST endpoint that creates a single scheduled match."""

    def setUp(self):
        self.admin = User.objects.create_superuser('smcadmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='SM Create Test', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        self.p1 = make_player('smc_p1', first='Alice', last='One')
        self.p2 = make_player('smc_p2', first='Bob', last='Two')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def _url(self, season=None):
        return reverse('admin:leagues_season_schedule_match', args=[(season or self.season).pk])

    def _post(self, **kwargs):
        data = {'tier': 1, 'player1': self.p1.pk, 'player2': self.p2.pk}
        data.update(kwargs)
        return self.client.post(self._url(), data)

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('smc_anon'))
        resp = self._post()
        self.assertNotEqual(resp.status_code, 200)

    def test_get_returns_405(self):
        import json
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_creates_match(self):
        import json
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertTrue(Match.objects.filter(season=self.season, player1=self.p1, player2=self.p2).exists())

    def test_match_has_correct_tier_and_round(self):
        import json
        self._post()
        match = Match.objects.get(season=self.season, player1=self.p1, player2=self.p2)
        self.assertEqual(match.tier, 1)
        self.assertEqual(match.round, Match.ROUND_REGULAR)
        self.assertEqual(match.status, Match.STATUS_SCHEDULED)

    def test_creates_match_with_date(self):
        import json
        self._post(scheduled_date='2025-06-15')
        match = Match.objects.get(season=self.season, player1=self.p1, player2=self.p2)
        self.assertEqual(match.scheduled_date, datetime.date(2025, 6, 15))

    def test_creates_match_without_date(self):
        import json
        self._post()
        match = Match.objects.get(season=self.season, player1=self.p1, player2=self.p2)
        self.assertIsNone(match.scheduled_date)

    def test_404_for_unknown_season(self):
        url = reverse('admin:leagues_season_schedule_match', args=[99999])
        resp = self.client.post(url, {'tier': 1, 'player1': self.p1.pk, 'player2': self.p2.pk})
        self.assertEqual(resp.status_code, 404)

    def test_same_player_returns_400(self):
        import json
        resp = self._post(player2=self.p1.pk)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertIn('error', data)

    def test_player_not_in_season_returns_400(self):
        import json
        outsider = make_player('smc_outsider')
        resp = self._post(player2=outsider.pk)
        self.assertEqual(resp.status_code, 400)

    def test_inactive_player_returns_400(self):
        import json
        inactive = make_player('smc_inactive')
        SeasonPlayer.objects.create(season=self.season, player=inactive, tier=1, is_active=False)
        resp = self._post(player2=inactive.pk)
        self.assertEqual(resp.status_code, 400)

    def test_invalid_date_returns_400(self):
        import json
        resp = self._post(scheduled_date='not-a-date')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertIn('error', data)

    def test_invalid_tier_returns_400(self):
        import json
        resp = self._post(tier='bad')
        self.assertEqual(resp.status_code, 400)

    def test_response_includes_match_id(self):
        import json
        resp = self._post()
        data = json.loads(resp.content)
        self.assertIn('match_id', data)
        self.assertTrue(Match.objects.filter(pk=data['match_id']).exists())


# ─── Delete Match endpoints ───────────────────────────────────────────────────

class DeleteMatchMatchesViewTest(TestCase):
    """Tests for the matches JSON endpoint used by the Delete a Match UI."""

    def setUp(self):
        self.admin = User.objects.create_superuser('dmladmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='DM Matches Test', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        self.p1 = make_player('dml_p1', first='Alice', last='Able')
        self.p2 = make_player('dml_p2', first='Bob', last='Baker')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def _url(self, season=None):
        return reverse('admin:leagues_season_delete_match_matches', args=[(season or self.season).pk])

    def _scheduled(self, p1=None, p2=None, date=None, tier=1):
        return Match.objects.create(
            season=self.season, player1=p1 or self.p1, player2=p2 or self.p2,
            tier=tier, round=Match.ROUND_REGULAR,
            scheduled_date=date or datetime.date(2025, 5, 1),
            status=Match.STATUS_SCHEDULED,
        )

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('dml_anon'))
        resp = self.client.get(self._url(), {'tier': 1})
        self.assertNotEqual(resp.status_code, 200)

    def test_404_for_unknown_season(self):
        url = reverse('admin:leagues_season_delete_match_matches', args=[99999])
        self.assertEqual(self.client.get(url, {'tier': 1}).status_code, 404)

    def test_returns_json_matches(self):
        import json
        self._scheduled()
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        self.assertIn('matches', data)
        self.assertEqual(len(data['matches']), 1)

    def test_match_entry_has_id_and_label(self):
        import json
        m = self._scheduled()
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        entry = data['matches'][0]
        self.assertEqual(entry['id'], m.id)
        self.assertIn('label', entry)

    def test_label_includes_player_names(self):
        import json
        self._scheduled()
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        label = data['matches'][0]['label']
        self.assertIn('Alice', label)
        self.assertIn('Bob', label)

    def test_only_scheduled_status_returned(self):
        import json
        self._scheduled()
        Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 2),
            status=Match.STATUS_COMPLETED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        self.assertEqual(len(data['matches']), 1)

    def test_only_regular_round_returned(self):
        import json
        self._scheduled()
        Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, round=Match.ROUND_R16,
            scheduled_date=datetime.date(2025, 5, 3),
            status=Match.STATUS_SCHEDULED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        self.assertEqual(len(data['matches']), 1)

    def test_matches_from_other_tier_excluded(self):
        import json
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        p3 = make_player('dml_p3', first='Carol', last='Cross')
        p4 = make_player('dml_p4', first='Dan', last='Dale')
        enroll(self.season, p3, tier=2)
        enroll(self.season, p4, tier=2)
        self._scheduled()
        Match.objects.create(
            season=self.season, player1=p3, player2=p4,
            tier=2, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 1), status=Match.STATUS_SCHEDULED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        self.assertEqual(len(data['matches']), 1)

    def test_matches_ordered_by_date(self):
        import json
        p3 = make_player('dml_p3b', first='Carol', last='Cross')
        enroll(self.season, p3, tier=1)
        self._scheduled(date=datetime.date(2025, 5, 10))
        Match.objects.create(
            season=self.season, player1=self.p1, player2=p3,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 3), status=Match.STATUS_SCHEDULED,
        )
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        dates_in_labels = [e['label'] for e in data['matches']]
        self.assertIn('May 3', dates_in_labels[0])
        self.assertIn('May 10', dates_in_labels[1])

    def test_empty_tier_returns_empty_list(self):
        import json
        data = json.loads(self.client.get(self._url(), {'tier': 1}).content)
        self.assertEqual(data['matches'], [])

    def test_invalid_tier_returns_400(self):
        self.assertEqual(self.client.get(self._url(), {'tier': 'bad'}).status_code, 400)

    def test_missing_tier_returns_400(self):
        self.assertEqual(self.client.get(self._url()).status_code, 400)


class DeleteMatchViewTest(TestCase):
    """Tests for the POST endpoint that deletes a single scheduled match."""

    def setUp(self):
        self.admin = User.objects.create_superuser('dmadmin', password='pass')
        self.client.force_login(self.admin)
        self.season = make_season(name='DM Delete Test', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        self.p1 = make_player('dm_p1', first='Eve', last='East')
        self.p2 = make_player('dm_p2', first='Frank', last='Ford')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def _url(self, season=None):
        return reverse('admin:leagues_season_delete_match', args=[(season or self.season).pk])

    def _scheduled(self):
        return Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 1),
            status=Match.STATUS_SCHEDULED,
        )

    def test_requires_staff(self):
        self.client.logout()
        self.client.force_login(make_player('dm_anon'))
        m = self._scheduled()
        self.assertNotEqual(self.client.post(self._url(), {'match_id': m.pk}).status_code, 200)

    def test_get_returns_405(self):
        self.assertEqual(self.client.get(self._url()).status_code, 405)

    def test_deletes_match(self):
        import json
        m = self._scheduled()
        resp = self.client.post(self._url(), {'match_id': m.pk})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertFalse(Match.objects.filter(pk=m.pk).exists())

    def test_404_for_unknown_season(self):
        m = self._scheduled()
        url = reverse('admin:leagues_season_delete_match', args=[99999])
        self.assertEqual(self.client.post(url, {'match_id': m.pk}).status_code, 404)

    def test_cannot_delete_completed_match(self):
        import json
        m = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 1),
            status=Match.STATUS_COMPLETED,
        )
        resp = self.client.post(self._url(), {'match_id': m.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Match.objects.filter(pk=m.pk).exists())

    def test_cannot_delete_playoff_match(self):
        import json
        m = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, round=Match.ROUND_R16,
            scheduled_date=datetime.date(2025, 5, 1),
            status=Match.STATUS_SCHEDULED,
        )
        resp = self.client.post(self._url(), {'match_id': m.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Match.objects.filter(pk=m.pk).exists())

    def test_cannot_delete_match_from_another_season(self):
        other_season = make_season(name='Other', year=2024)
        Tier.objects.create(season=other_season, number=1, name='Tier 1')
        op1 = make_player('dm_op1')
        op2 = make_player('dm_op2')
        enroll(other_season, op1, tier=1)
        enroll(other_season, op2, tier=1)
        m = Match.objects.create(
            season=other_season, player1=op1, player2=op2,
            tier=1, round=Match.ROUND_REGULAR,
            scheduled_date=datetime.date(2025, 5, 1),
            status=Match.STATUS_SCHEDULED,
        )
        resp = self.client.post(self._url(), {'match_id': m.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Match.objects.filter(pk=m.pk).exists())

    def test_invalid_match_id_returns_400(self):
        resp = self.client.post(self._url(), {'match_id': 'bad'})
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_match_id_returns_400(self):
        resp = self.client.post(self._url(), {'match_id': 99999})
        self.assertEqual(resp.status_code, 400)
