import pytest
from playwright.sync_api import Page, expect

DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 375, "height": 812}


def _standings_url(live_server, season):
    return f"{live_server.url}/seasons/{season.slug}/standings/"


def _results_url(live_server, season):
    return f"{live_server.url}/seasons/{season.slug}/results/"


def _matchups_url(live_server, season):
    return f"{live_server.url}/seasons/{season.slug}/matchups/"


@pytest.mark.django_db(transaction=True)
def test_standings_desktop(page: Page, live_server, season, players, completed_matches):
    page.set_viewport_size(DESKTOP)
    page.goto(_standings_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("standings-desktop.png", max_diff_pixel_ratio=0.02)


@pytest.mark.django_db(transaction=True)
def test_standings_mobile(page: Page, live_server, season, players, completed_matches):
    page.set_viewport_size(MOBILE)
    page.goto(_standings_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("standings-mobile.png", max_diff_pixel_ratio=0.02)


@pytest.mark.django_db(transaction=True)
def test_results_desktop(page: Page, live_server, season, players, completed_matches):
    page.set_viewport_size(DESKTOP)
    page.goto(_results_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("results-desktop.png", max_diff_pixel_ratio=0.02)


@pytest.mark.django_db(transaction=True)
def test_results_mobile(page: Page, live_server, season, players, completed_matches):
    page.set_viewport_size(MOBILE)
    page.goto(_results_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("results-mobile.png", max_diff_pixel_ratio=0.02)


@pytest.mark.django_db(transaction=True)
def test_matchups_desktop(page: Page, live_server, season, players, scheduled_matches):
    page.set_viewport_size(DESKTOP)
    page.goto(_matchups_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("matchups-desktop.png", max_diff_pixel_ratio=0.02)


@pytest.mark.django_db(transaction=True)
def test_matchups_mobile(page: Page, live_server, season, players, scheduled_matches):
    page.set_viewport_size(MOBILE)
    page.goto(_matchups_url(live_server, season))
    page.wait_for_load_state("networkidle")
    expect(page).to_have_screenshot("matchups-mobile.png", max_diff_pixel_ratio=0.02)
