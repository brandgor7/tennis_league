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
    document.addEventListener('DOMContentLoaded', function () {
        var enforce = document.getElementById('id_enforce_scheduled_dates');
        if (!enforce) return;
        toggleDateFields();
        enforce.addEventListener('change', toggleDateFields);
    });
}());
