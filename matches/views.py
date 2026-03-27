import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView, DetailView

from leagues.models import Season
from .forms import ResultEntryForm, WalkoverForm, PostponeForm
from .models import Match, MatchSet


def _get_player_match(request, pk):
    """Load a match; require the requesting user to be one of its players or staff."""
    match = get_object_or_404(
        Match.objects.select_related('player1', 'player2', 'season'),
        pk=pk,
    )
    if not (request.user == match.player1 or request.user == match.player2 or request.user.is_staff):
        raise PermissionDenied
    return match


class MatchupsView(TemplateView):
    template_name = 'matches/matchups.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, pk=self.kwargs['pk'])
        qs = (
            Match.objects
            .filter(season=season, status__in=[Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED, Match.STATUS_PENDING])
            .select_related('player1', 'player2', 'winner')
            .order_by(F('scheduled_date').asc(nulls_last=True), 'created_at')
        )
        multi_tier = season.num_tiers > 1
        tiers = [
            (tier_num, qs.filter(tier=tier_num))
            for tier_num in range(1, season.num_tiers + 1)
        ] if multi_tier else [(1, qs)]
        ctx['season'] = season
        ctx['tiers'] = tiers
        ctx['multi_tier'] = multi_tier
        return ctx


class ResultsView(TemplateView):
    template_name = 'matches/results.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, pk=self.kwargs['pk'])
        qs = (
            Match.objects
            .filter(season=season, status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER])
            .select_related('player1', 'player2', 'winner')
            .prefetch_related('sets')
            .order_by(F('played_date').desc(nulls_last=True), '-created_at')
        )
        multi_tier = season.num_tiers > 1
        tiers = [
            (tier_num, qs.filter(tier=tier_num))
            for tier_num in range(1, season.num_tiers + 1)
        ] if multi_tier else [(1, qs)]
        ctx['season'] = season
        ctx['tiers'] = tiers
        ctx['multi_tier'] = multi_tier
        return ctx


class MatchDetailView(DetailView):
    model = Match
    template_name = 'matches/match_detail.html'
    context_object_name = 'match'

    def get_queryset(self):
        return Match.objects.select_related('player1', 'player2', 'winner', 'season')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['season'] = self.object.season
        ctx['multi_tier'] = self.object.season.num_tiers > 1
        ctx['sets'] = self.object.sets.all()
        return ctx


class EnterResultView(LoginRequiredMixin, View):
    template_name = 'matches/enter_result.html'

    def _build_context(self, form, match):
        season = match.season
        max_sets = season.max_sets_in_match

        sets_meta = []
        for i in range(1, max_sets + 1):
            is_final = (i == max_sets)
            is_super = is_final and season.is_super_final_format
            meta = {
                'set_num': i,
                'is_final': is_final,
                'is_super': is_super,
                'is_final_tb': is_final and season.is_tiebreak_final_format,
                'p1_field': form[f'set{i}_p1'],
                'p2_field': form[f'set{i}_p2'],
            }
            if not is_super:
                meta['tb_p1_field'] = form[f'set{i}_tb_p1']
                meta['tb_p2_field'] = form[f'set{i}_tb_p2']
            sets_meta.append(meta)

        return {
            'form': form,
            'match': match,
            'season': season,
            'multi_tier': season.num_tiers > 1,
            'sets_meta': sets_meta,
            'max_sets': max_sets,
            'games_to_win_set': season.games_to_win_set,
            'player1_name': match.player1.get_full_name() or match.player1.username,
            'player2_name': match.player2.get_full_name() or match.player2.username,
        }

    def _check_can_enter(self, request, match):
        if match.status not in [Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED]:
            messages.error(request, 'Results can only be entered for scheduled or postponed matches.')
            return False
        if match.scheduled_date:
            grace = match.season.grace_period_days
            deadline = match.scheduled_date + datetime.timedelta(days=grace)
            if datetime.date.today() > deadline:
                messages.error(
                    request,
                    f'This match is more than {grace} day{"s" if grace != 1 else ""} past its scheduled date. '
                    'Please postpone it with a new date before entering the result.',
                )
                return False
        return True

    def get(self, request, pk):
        match = _get_player_match(request, pk)
        if not self._check_can_enter(request, match):
            return redirect('matches:match_detail', pk=pk)
        form = ResultEntryForm(match=match)
        return render(request, self.template_name, self._build_context(form, match))

    def post(self, request, pk):
        match = _get_player_match(request, pk)
        if not self._check_can_enter(request, match):
            return redirect('matches:match_detail', pk=pk)

        form = ResultEntryForm(request.POST, match=match)
        if form.is_valid():
            season = match.season
            cleaned = form.cleaned_data

            with transaction.atomic():
                match.sets.all().delete()
                for i in range(1, form.max_sets + 1):
                    p1 = cleaned.get(f'set{i}_p1')
                    p2 = cleaned.get(f'set{i}_p2')
                    if p1 is None or p2 is None:
                        continue
                    is_super = (i == form.max_sets) and season.is_super_final_format
                    MatchSet.objects.create(
                        match=match,
                        set_number=i,
                        player1_games=p1,
                        player2_games=p2,
                        tiebreak_player1_points=None if is_super else cleaned.get(f'set{i}_tb_p1'),
                        tiebreak_player2_points=None if is_super else cleaned.get(f'set{i}_tb_p2'),
                    )
                match.status = Match.STATUS_PENDING
                match.entered_by = request.user
                match.save()

            messages.success(request, 'Score submitted — awaiting confirmation from your opponent.')
            return redirect('matches:match_detail', pk=pk)

        return render(request, self.template_name, self._build_context(form, match))


class ConfirmResultView(LoginRequiredMixin, View):
    template_name = 'matches/confirm_result.html'

    def _get_match(self, request, pk):
        match = get_object_or_404(
            Match.objects.select_related('player1', 'player2', 'season', 'entered_by'),
            pk=pk,
        )
        # Check authorization before status so unauthorized users always get 403
        is_player = request.user in (match.player1, match.player2)
        is_other_player = is_player and request.user != match.entered_by
        if not (is_other_player or request.user.is_staff):
            raise PermissionDenied
        if match.status != Match.STATUS_PENDING:
            messages.error(request, 'This match is not awaiting confirmation.')
            return None
        return match

    def get(self, request, pk):
        match = self._get_match(request, pk)
        if match is None:
            return redirect('matches:match_detail', pk=pk)
        sets = match.sets.all()
        return render(request, self.template_name, {
            'match': match,
            'season': match.season,
            'multi_tier': match.season.num_tiers > 1,
            'sets': sets,
            'is_walkover': not sets,
        })

    def post(self, request, pk):
        match = self._get_match(request, pk)
        if match is None:
            return redirect('matches:match_detail', pk=pk)

        action = request.POST.get('action')
        if action == 'confirm':
            with transaction.atomic():
                sets = list(match.sets.select_for_update().all())
                if not sets:
                    # Walkover confirmation — winner already set by WalkoverView
                    match.status = Match.STATUS_WALKOVER
                    match.confirmed_by = request.user
                    match.played_date = datetime.date.today()
                    match.save(update_fields=['status', 'confirmed_by', 'played_date'])
                    messages.success(request, 'Walkover confirmed.')
                else:
                    p1_sets = sum(1 for s in sets if s.player1_games > s.player2_games)
                    p2_sets = sum(1 for s in sets if s.player2_games > s.player1_games)
                    if p1_sets == p2_sets:
                        messages.error(request, 'Cannot confirm: sets are tied. Please contact the administrator.')
                        return redirect('matches:match_detail', pk=pk)
                    winner = match.player1 if p1_sets > p2_sets else match.player2
                    match.status = Match.STATUS_COMPLETED
                    match.confirmed_by = request.user
                    match.played_date = datetime.date.today()
                    match.winner = winner
                    match.save()
                    messages.success(request, 'Result confirmed. Match is now complete.')
            return redirect('matches:match_detail', pk=pk)

        elif action == 'dispute':
            with transaction.atomic():
                match.sets.all().delete()
                match.status = Match.STATUS_SCHEDULED
                match.entered_by = None
                match.winner = None
                match.walkover_reason = ''
                match.save()
            messages.warning(
                request,
                'Result disputed. The match has been reset to scheduled. '
                'Please contact the administrator to resolve the discrepancy.',
            )
            return redirect('matches:match_detail', pk=pk)

        # Unknown action — re-render
        sets = match.sets.all()
        return render(request, self.template_name, {
            'match': match,
            'season': match.season,
            'multi_tier': match.season.num_tiers > 1,
            'sets': sets,
            'is_walkover': not sets,
        })


class WalkoverView(LoginRequiredMixin, View):
    template_name = 'matches/walkover.html'

    def _context(self, form, match):
        return {
            'form': form,
            'match': match,
            'season': match.season,
            'multi_tier': match.season.num_tiers > 1,
        }

    def get(self, request, pk):
        match = _get_player_match(request, pk)
        return render(request, self.template_name, self._context(WalkoverForm(match=match), match))

    def post(self, request, pk):
        match = _get_player_match(request, pk)
        if match.status not in [Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED]:
            messages.error(request, 'Walkovers can only be recorded for scheduled or postponed matches.')
            return redirect('matches:match_detail', pk=pk)
        form = WalkoverForm(request.POST, match=match)
        if form.is_valid():
            winner_choice = form.cleaned_data['winner']
            winner = match.player1 if winner_choice == WalkoverForm.WINNER_P1 else match.player2
            match.status = Match.STATUS_PENDING
            match.winner = winner
            match.walkover_reason = form.cleaned_data['reason']
            match.entered_by = request.user
            match.save(update_fields=['status', 'winner', 'walkover_reason', 'entered_by'])
            messages.success(request, 'Walkover submitted — awaiting confirmation from the other player.')
            return redirect('matches:match_detail', pk=pk)
        return render(request, self.template_name, self._context(form, match))


class PostponeView(LoginRequiredMixin, View):
    template_name = 'matches/postpone.html'

    def _context(self, form, match):
        return {
            'form': form,
            'match': match,
            'season': match.season,
            'multi_tier': match.season.num_tiers > 1,
        }

    def get(self, request, pk):
        match = _get_player_match(request, pk)
        return render(request, self.template_name, self._context(PostponeForm(), match))

    def post(self, request, pk):
        match = _get_player_match(request, pk)
        if match.status not in [Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED]:
            messages.error(request, 'Only scheduled or postponed matches can be rescheduled.')
            return redirect('matches:match_detail', pk=pk)
        form = PostponeForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason'].strip()
            match.scheduled_date = form.cleaned_data['new_date']
            match.status = Match.STATUS_POSTPONED
            if reason:
                existing = match.notes.strip()
                match.notes = f'{existing}\nPostponed: {reason}'.strip()
            match.save(update_fields=['scheduled_date', 'status', 'notes'])
            messages.success(request, 'Match postponed and rescheduled.')
            return redirect('matches:match_detail', pk=pk)
        return render(request, self.template_name, self._context(form, match))
