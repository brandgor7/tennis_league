(function () {
    'use strict';
    function toggleDateFields() {
        var enforce = document.getElementById('id_enforce_scheduled_dates');
        var deadline = document.getElementById('id_postponement_deadline');
        var grace = document.getElementById('id_grace_period_days');
        if (!enforce || !deadline || !grace) return;
        var enabled = enforce.checked;
        deadline.closest('.form-row, .field-postponement_deadline, .field-box')
            .style.opacity = enabled ? '' : '0.4';
        grace.closest('.form-row, .field-grace_period_days, .field-box')
            .style.opacity = enabled ? '' : '0.4';
    }

    function toggleScheduleDays() {
        var mode = document.getElementById('id_schedule_display_mode');
        var days = document.getElementById('id_schedule_display_days');
        if (!mode || !days) return;
        var enabled = mode.value === 'next_x_days';
        // grey out the field container
        var container = days.closest('.form-row, .field-schedule_display_days, .field-box');
        if (container) container.style.opacity = enabled ? '' : '0.4';
        // disable input so it's not editable when not applicable
        days.disabled = !enabled;
    }

    function toggleUseTeamName() {
        var ppt = document.getElementById('id_players_per_team');
        var utn = document.getElementById('id_use_team_name');
        if (!ppt || !utn) return;
        var enabled = parseInt(ppt.value, 10) > 1;
        var container = utn.closest('.form-row, .field-use_team_name, .field-box');
        if (container) container.style.opacity = enabled ? '' : '0.4';
        utn.disabled = !enabled;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var enforce = document.getElementById('id_enforce_scheduled_dates');
        if (enforce) {
            toggleDateFields();
            enforce.addEventListener('change', toggleDateFields);
        }

        var mode = document.getElementById('id_schedule_display_mode');
        if (mode) {
            toggleScheduleDays();
            mode.addEventListener('change', toggleScheduleDays);
        }

        var ppt = document.getElementById('id_players_per_team');
        if (ppt) {
            toggleUseTeamName();
            ppt.addEventListener('change', toggleUseTeamName);
        }
    });
}());
