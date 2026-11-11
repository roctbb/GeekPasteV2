(function () {
    'use strict';

    function filterTests(report, filter) {
        report.dataset.testFilter = filter;
        report.querySelectorAll('[data-test-status]').forEach(function (row) {
            row.hidden = filter === 'failed' && row.dataset.testStatus === 'passed';
        });
        report.querySelectorAll('[data-test-filter]').forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.dataset.testFilter === filter));
        });
    }

    function paintReport(container, html, preserveState) {
        var previous = container.querySelector('.io-test-report');
        var open = previous ? previous.open : null;
        var filter = previous ? previous.dataset.testFilter : null;
        container.hidden = !html;
        container.innerHTML = html;
        var report = container.querySelector('.io-test-report');
        if (!report) return;
        if (preserveState && open !== null) report.open = open;
        var filters = report.querySelector('.io-test-filters');
        if (filters) {
            filters.hidden = false;
            filterTests(report, preserveState && filter ? filter : 'failed');
        }
        if (container.dataset.hiddenTestsUrl && report.querySelector('[data-test-private="true"]')) {
            if (!filters) {
                filters = document.createElement('div');
                filters.className = 'io-test-filters';
                report.querySelector('.io-test-report-body').prepend(filters);
            }
            var state = container.privateTestsState;
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-sm btn-outline-secondary';
            button.dataset.hiddenTestsToggle = '';
            button.disabled = state.loading;
            button.setAttribute('aria-pressed', String(state.revealed));
            button.textContent = state.loading ? 'Загружаем…' : (state.revealed ? 'Скрыть данные тестов' : 'Показать скрытые тесты');
            filters.append(button);
            if (state.error) {
                var error = document.createElement('span');
                error.className = 'small text-danger';
                error.setAttribute('role', 'status');
                error.textContent = 'Не удалось загрузить скрытые тесты. Повторите попытку.';
                filters.append(error);
            }
        }
    }

    async function revealTests(container) {
        var state = container.privateTestsState;
        if (state.loading) return;
        state.error = false;
        if (state.revealed) {
            state.revealed = false;
            paintReport(container, container.reportHtml, true);
            return;
        }
        if (state.html) {
            state.revealed = true;
            paintReport(container, state.html, true);
            return;
        }
        var requestId = ++state.requestId;
        state.loading = true;
        paintReport(container, container.reportHtml, true);
        try {
            var response = await fetch(container.dataset.hiddenTestsUrl, {credentials: 'same-origin', cache: 'no-store'});
            if (!response.ok || response.redirected) throw new Error('Unavailable');
            var data = await response.json();
            if (typeof data.test_results_html !== 'string' || !data.test_results_html) throw new Error('Unavailable');
            if (state.requestId !== requestId) return;
            state.html = data.test_results_html;
            state.revealed = true;
        } catch (error) {
            if (state.requestId !== requestId) return;
            state.error = true;
        } finally {
            if (state.requestId === requestId) {
                state.loading = false;
                paintReport(container, state.revealed ? state.html : container.reportHtml, true);
            }
        }
    }

    window.renderSubmissionTests = function (container, html) {
        if (!container) return;
        var nextHtml = typeof html === 'string' ? html : '';
        // Shared status events contain public data only. Keep teacher-only data
        // local to this viewer and invalidate it whenever the result changes.
        if (container.reportHtml === nextHtml) return;
        var state = container.privateTestsState || {requestId: 0};
        state.requestId++;
        state.html = null;
        state.revealed = false;
        state.loading = false;
        state.error = false;
        container.privateTestsState = state;
        container.reportHtml = nextHtml;
        paintReport(container, nextHtml, false);
    };

    document.addEventListener('click', function (event) {
        var privateToggle = event.target.closest('[data-hidden-tests-toggle]');
        if (privateToggle) {
            var container = privateToggle.closest('[data-hidden-tests-url]');
            if (container) revealTests(container);
            return;
        }
        var button = event.target.closest('[data-test-filter]');
        if (!button) return;
        var report = button.closest('.io-test-report');
        if (report) filterTests(report, button.dataset.testFilter);
    });
}());
