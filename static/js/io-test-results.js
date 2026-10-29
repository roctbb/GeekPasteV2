(function () {
    'use strict';

    function filterTests(report, filter) {
        report.querySelectorAll('[data-test-status]').forEach(function (row) {
            row.hidden = filter === 'failed' && row.dataset.testStatus === 'passed';
        });
        report.querySelectorAll('[data-test-filter]').forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.dataset.testFilter === filter));
        });
    }

    window.renderSubmissionTests = function (container, html) {
        if (!container) return;
        var nextHtml = typeof html === 'string' ? html : '';
        // Repeated status events must not reset the reader's open/closed state or filter.
        if (container.reportHtml === nextHtml) return;
        container.reportHtml = nextHtml;
        container.hidden = !nextHtml;
        container.innerHTML = nextHtml;
        var report = container.querySelector('.io-test-report');
        if (!report) return;
        var filters = report.querySelector('.io-test-filters');
        if (filters) {
            filters.hidden = false;
            filterTests(report, 'failed');
        }
    };

    document.addEventListener('click', function (event) {
        var button = event.target.closest('[data-test-filter]');
        if (!button) return;
        var report = button.closest('.io-test-report');
        if (report) filterTests(report, button.dataset.testFilter);
    });
}());
