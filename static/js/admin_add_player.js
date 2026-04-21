document.addEventListener('DOMContentLoaded', function () {
    const firstName = document.getElementById('id_first_name');
    const lastName = document.getElementById('id_last_name');
    const username = document.getElementById('id_username');
    const setPassword = document.getElementById('id_set_password');
    const pwRow1 = document.querySelector('.field-password1');
    const pwRow2 = document.querySelector('.field-password2');

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
            usernameEdited = username.value.length > 0;
        });
    }

    function togglePassword() {
        const show = setPassword?.checked;
        if (pwRow1) pwRow1.style.display = show ? '' : 'none';
        if (pwRow2) pwRow2.style.display = show ? '' : 'none';
    }

    if (setPassword) {
        setPassword.addEventListener('change', togglePassword);
        togglePassword();
    }
});
