(function () {
    'use strict';

    function fieldRow(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        return el.closest('.form-row, .field-box') || el.parentElement;
    }

    function toggleSide(n) {
        var checkbox = document.getElementById('id_player' + n + '_is_external');
        if (!checkbox) return;
        var playerRow = fieldRow('id_player' + n);
        var playerSelect = document.getElementById('id_player' + n);
        var external = checkbox.checked;

        if (playerRow) playerRow.style.display = external ? 'none' : '';

        if (external && playerSelect) {
            if (window.django && django.jQuery) {
                django.jQuery(playerSelect).val('').trigger('change');
            } else {
                playerSelect.value = '';
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        ['1', '2'].forEach(function (n) {
            var checkbox = document.getElementById('id_player' + n + '_is_external');
            if (!checkbox) return;
            toggleSide(n);
            checkbox.addEventListener('change', function () { toggleSide(n); });
        });
    });
}());
