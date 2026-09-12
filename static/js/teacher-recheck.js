(function () {
    'use strict';
    var section = document.getElementById('teacher-recheck');
    if (!section) return;
    var toggle = document.getElementById('teacher-recheck-toggle');
    var form = document.getElementById('teacher-recheck-form');
    var comment = document.getElementById('teacher-recheck-comment');
    var submit = document.getElementById('teacher-recheck-submit');
    var message = document.getElementById('teacher-recheck-message');
    var url = '/submission/recheck?id=' + encodeURIComponent(section.dataset.codeId);
    var requested = false;
    var busy = false;
    var opened = false;

    async function check(send) {
        if (busy || requested) return;
        busy = true;
        toggle.disabled = true;
        submit.disabled = true;
        message.textContent = send ? 'Отправляем запрос…' : 'Проверяем статус…';
        try {
            var options = {credentials: 'same-origin', headers: {'Accept': 'application/json'}};
            if (send) {
                options.method = 'POST';
                options.headers['Content-Type'] = 'application/json';
                options.headers['X-CSRF-Token'] = section.dataset.csrf;
                options.body = JSON.stringify({comment: comment.value.trim()});
            }
            var response = await fetch(url, options);
            var data = await response.json();
            if (data.state !== 'ok') throw new Error(data.message || 'Не удалось получить статус. Попробуйте ещё раз.');
            requested = data.requested;
            form.hidden = requested || !data.available || !opened;
            message.textContent = data.message || '';
            if (requested) {
                toggle.hidden = true;
                if (data.comment) message.textContent += '\nВаш комментарий: ' + data.comment;
                message.style.whiteSpace = 'pre-wrap';
            } else if (data.available && opened) {
                comment.focus();
            }
        } catch (error) {
            // Keep the comment for safe retries, including an uncertain POST outcome.
            message.textContent = error.message || 'Не удалось отправить запрос. Попробуйте ещё раз.';
        } finally {
            busy = false;
            toggle.disabled = false;
            submit.disabled = false;
        }
    }
    toggle.addEventListener('click', function () { opened = true; check(false); });
    form.addEventListener('submit', function (event) {
        event.preventDefault();
        if (form.reportValidity()) check(true);
    });
    check(false);
}());
