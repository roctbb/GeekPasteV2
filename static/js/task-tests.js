(() => {
    'use strict';
    const form = document.getElementById('task-form');
    if (!form) return;
    const byId = id => document.getElementById(id);
    const mode = byId('test-mode');
    const checkType = form.elements.check_type;
    const scoring = byId('test-scoring');
    const comparison = byId('test-comparison');
    const cases = byId('test-cases');
    const groups = byId('test-groups');
    const add = byId('add-test');
    let groupSequence = 0;
    const toggle = (id, enabled) => {
        const fieldset = byId(id);
        fieldset.hidden = !enabled;
        fieldset.disabled = !enabled;
    };
    function refreshGroups() {
        const rows = [...groups.children];
        const enabled = scoring.value === 'groups';
        cases.querySelectorAll('[name="test_group"]').forEach(select => {
            const selected = select.value;
            select.replaceChildren(new Option('Выберите группу', ''));
            rows.forEach(row => select.add(new Option(
                row.querySelector('[name="group_name"]').value || 'Без названия',
                row.querySelector('[name="group_id"]').value
            )));
            select.value = selected;
            select.disabled = !enabled;
            select.required = enabled;
            select.closest('.case-group').hidden = !enabled;
        });
        byId('add-group').disabled = rows.length >= 50;
    }
    function refreshCases() {
        [...cases.children].forEach((row, index) => {
            row.querySelector('.test-number').textContent = `Тест ${index + 1}`;
            row.querySelector('[data-action="up"]').disabled = index === 0;
            row.querySelector('[data-action="down"]').disabled = index === cases.children.length - 1;
            row.querySelectorAll('[data-file]').forEach(input => {
                input.name = `test_${input.dataset.file}_file_${index}`;
            });
        });
        add.disabled = cases.children.length >= 50;
        byId('test-count').textContent = `${cases.children.length} из 50 тестов`;
        refreshGroups();
    }
    function addCase() {
        if (cases.children.length >= 50) return;
        cases.append(byId('test-case-template').content.cloneNode(true));
        refreshCases();
    }
    function refreshSettings() {
        const isTests = checkType.value === 'tests';
        const isIO = isTests && mode.value === 'io';
        byId('test-settings').hidden = !isTests;
        toggle('io-test-settings', isIO);
        byId('environment-help').hidden = isIO;
        toggle('test-group-settings', scoring.value === 'groups');
        const comparisons = [comparison.value, ...[...cases.querySelectorAll('[name="test_case_comparison"]')].map(select => select.value)];
        toggle('exact-settings', comparisons.includes('exact'));
        toggle('float-settings', comparisons.includes('float'));
        byId('comparison-help').textContent = comparison.value === 'rational_absolute'
            ? 'Эталон записывается как числитель/знаменатель (например, 1/3). Ответ программы — десятичное число с абсолютной погрешностью не больше 0.000001.'
            : 'Правила сравнения применяются буквально. В режиме «По словам и числам» значения 1 и 1.0 различаются. Сравнение конца вывода разрешает текст приглашений перед ответом.';
        byId('scoring-help').textContent = {
            proportional: 'Максимум × доля пройденных тестов, с округлением вниз.',
            all_or_nothing: 'Полный балл за все пройденные тесты. Иначе — только действующий минимальный балл за попытку.',
            groups: 'Складываются баллы полностью пройденных групп.'
        }[scoring.value];
        if (isIO && !cases.children.length) addCase();
        refreshGroups();
    }
    cases.addEventListener('change', event => {
        if (event.target.name === 'test_case_comparison') refreshSettings();
    });
    cases.addEventListener('click', async event => {
        const button = event.target.closest('[data-field-action]');
        if (!button) return;
        const field = button.closest('.io-test-field');
        const textarea = field.querySelector('textarea');
        const reference = field.querySelector('input[type="hidden"]');
        const status = field.querySelector('.field-load-status');
        const actions = field.querySelectorAll('[data-field-action]');
        actions.forEach(action => { action.disabled = true; });
        try {
            let text = '';
            if (button.dataset.fieldAction === 'load') {
                status.textContent = 'Загрузка текста…';
                const response = await fetch(button.dataset.url, {credentials: 'same-origin', redirect: 'error'});
                if (!response.ok) throw new Error('Не удалось загрузить данные. Возможно, тест изменился — откройте редактор заново.');
                text = await response.text();
            }
            textarea.value = text;
            textarea.hidden = false;
            reference.value = '';
            field.querySelector('.saved-test-field').hidden = true;
            textarea.focus();
        } catch (error) {
            status.textContent = error.message || 'Не удалось загрузить текст.';
            actions.forEach(action => { action.disabled = false; });
        }
    });
    add.addEventListener('click', () => {
        addCase();
        cases.lastElementChild.querySelector('textarea').focus();
    });
    cases.addEventListener('click', event => {
        const button = event.target.closest('[data-action]');
        if (!button) return;
        const row = button.closest('.io-test-case');
        if (button.dataset.action === 'remove') row.remove();
        if (button.dataset.action === 'up' && row.previousElementSibling) row.previousElementSibling.before(row);
        if (button.dataset.action === 'down' && row.nextElementSibling) row.nextElementSibling.after(row);
        refreshCases();
        refreshSettings();
    });
    byId('add-group').addEventListener('click', () => {
        if (groups.children.length >= 50) return;
        const fragment = byId('test-group-template').content.cloneNode(true);
        fragment.querySelector('[name="group_id"]').value = `g-${Date.now()}-${++groupSequence}`;
        fragment.querySelector('[name="group_name"]').value = `Группа ${groups.children.length + 1}`;
        groups.append(fragment);
        refreshGroups();
    });
    groups.addEventListener('input', refreshGroups);
    groups.addEventListener('click', event => {
        const button = event.target.closest('[data-action="remove-group"]');
        if (button) {
            button.closest('.io-test-group').remove();
            refreshGroups();
        }
    });
    [mode, checkType, scoring, comparison].forEach(input => input.addEventListener('change', refreshSettings));
    refreshCases();
    refreshSettings();
})();
