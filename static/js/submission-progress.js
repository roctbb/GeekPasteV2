(function () {
    'use strict';
    var messages = {
        queued: 'Решение ожидает своей очереди.',
        preparing: 'Подготавливаем среду для запуска решения.',
        compiling: 'Компилируем программу.',
        testing: 'Выполняем тесты.',
        unknown: 'Ожидаем обновления статуса. Результат появится здесь автоматически.'
    };

    window.renderSubmissionProgress = function (container, payload) {
        if (!container) return;
        container.hidden = payload.check_state !== 'not checked';
        if (container.hidden) return;
        var progress = payload.check_progress || {phase: 'unknown'};
        var steps = Array.from(container.querySelectorAll('[data-check-phase]'));
        var current = steps.findIndex(function (step) { return step.dataset.checkPhase === progress.phase; });
        steps.forEach(function (step, index) {
            step.classList.toggle('is-complete', current >= 0 && index < current);
            step.classList.toggle('is-current', index === current);
            if (index === current) step.setAttribute('aria-current', 'step');
            else step.removeAttribute('aria-current');
        });
        var message = messages[progress.phase] || messages.unknown;
        var meter = container.querySelector('progress');
        var hasCount = progress.phase === 'testing' && Number.isInteger(progress.total) &&
            Number.isInteger(progress.completed) && progress.total > 0 &&
            progress.completed >= 0 && progress.completed <= progress.total;
        meter.hidden = !hasCount;
        if (hasCount) {
            meter.max = progress.total;
            meter.value = progress.completed;
            message = 'Завершено тестов: ' + progress.completed + ' из ' + progress.total + '.';
        }
        var label = container.querySelector('[role="status"]');
        if (label.textContent !== message) label.textContent = message;
    };
}());
