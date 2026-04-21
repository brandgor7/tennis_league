document.addEventListener('DOMContentLoaded', function () {
    const firstName = document.getElementById('id_first_name');
    const lastName = document.getElementById('id_last_name');
    const username = document.getElementById('id_username');
    const setPassword = document.getElementById('id_set_password');
    const pwRow1 = document.querySelector('.field-password1');
    const pwRow2 = document.querySelector('.field-password2');
    const seasonSelect = document.getElementById('id_season');

    // --- Username auto-populate ---

    let usernameEdited = false;

    function slugify(s) {
        return s.toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    function autoUsername() {
        if (usernameEdited || !username) return;
        username.value = slugify(firstName?.value || '') + slugify(lastName?.value || '');
    }

    if (firstName) firstName.addEventListener('input', autoUsername);
    if (lastName) lastName.addEventListener('input', autoUsername);
    if (username) {
        username.addEventListener('input', function () {
            // Stop auto-fill once user types; resume if they clear the field entirely.
            usernameEdited = username.value.length > 0;
        });
    }

    // --- Password toggle ---

    function togglePassword() {
        const show = setPassword?.checked;
        if (pwRow1) pwRow1.style.display = show ? '' : 'none';
        if (pwRow2) pwRow2.style.display = show ? '' : 'none';
    }

    if (setPassword) {
        setPassword.addEventListener('change', togglePassword);
        togglePassword();
    }

    // --- Tier select: populate from season ---

    const tierRow = document.querySelector('.field-tier');

    function buildTierSelect(tiers) {
        const sel = document.createElement('select');
        sel.name = 'tier';
        sel.id = 'id_tier';
        tiers.forEach(function (t) {
            const opt = document.createElement('option');
            opt.value = t.number;
            opt.textContent = t.name + ' (' + t.number + ')';
            sel.appendChild(opt);
        });
        return sel;
    }

    function restoreIntegerInput() {
        const existing = document.getElementById('id_tier');
        if (existing && existing.tagName === 'SELECT') {
            const input = document.createElement('input');
            input.type = 'number';
            input.name = 'tier';
            input.id = 'id_tier';
            input.min = '1';
            input.value = '1';
            existing.replaceWith(input);
        }
    }

    async function loadTiers(seasonId) {
        if (!seasonId || !tierRow) return;
        const url = seasonSelect.dataset.tiersUrl + '?season_id=' + seasonId;
        try {
            const resp = await fetch(url);
            const tiers = await resp.json();
            const existing = document.getElementById('id_tier');
            if (tiers.length === 0) {
                restoreIntegerInput();
                return;
            }
            const sel = buildTierSelect(tiers);
            existing.replaceWith(sel);
        } catch (_) {
            restoreIntegerInput();
        }
    }

    if (seasonSelect) {
        seasonSelect.addEventListener('change', function () {
            if (this.value) {
                loadTiers(this.value);
            } else {
                restoreIntegerInput();
            }
        });
    }
});
