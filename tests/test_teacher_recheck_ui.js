// Run with node tests/test_teacher_recheck_ui.js; no browser/network dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync(require('node:path').join(__dirname, '../static/js/teacher-recheck.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function scenario(initial) {
    const elements = {};
    for (const id of ['teacher-recheck', 'teacher-recheck-toggle', 'teacher-recheck-form', 'teacher-recheck-comment', 'teacher-recheck-submit', 'teacher-recheck-message']) {
        elements[id] = {dataset: {codeId: 'TEST', csrf: 'CSRF'}, hidden: id.endsWith('form'), style: {},
            value: '', textContent: '', handlers: {}, focus() {}, reportValidity() { return true; },
            addEventListener(name, callback) { this.handlers[name] = callback; }};
    }
    const calls = [];
    let answer = initial;
    vm.runInNewContext(script, {document: {getElementById: id => elements[id]},
        fetch: async (url, options) => { calls.push({url, options}); return {json: async () => answer}; }});
    await tick();
    return {elements, calls, respond(value) { answer = value; }};
}

(async () => {
    const ready = {state: 'ok', requested: false, available: true};
    const ui = await scenario(ready);
    const e = ui.elements;
    assert.equal(e['teacher-recheck-form'].hidden, true);
    e['teacher-recheck-toggle'].handlers.click();
    await tick();
    assert.equal(e['teacher-recheck-form'].hidden, false);
    e['teacher-recheck-comment'].value = '  Прошу проверить критерий  ';
    ui.respond({state: 'error', message: 'Временно недоступно'});
    e['teacher-recheck-form'].handlers.submit({preventDefault() {}});
    await tick();
    assert.equal(e['teacher-recheck-comment'].value, '  Прошу проверить критерий  ');
    assert.equal(e['teacher-recheck-message'].textContent, 'Временно недоступно');
    const posted = ui.calls.at(-1).options;
    assert.equal(posted.headers['X-CSRF-Token'], 'CSRF');
    assert.equal(JSON.parse(posted.body).comment, 'Прошу проверить критерий');
    ui.respond({state: 'ok', requested: true, available: false, message: 'Отправлено', comment: '<script>not HTML</script>'});
    e['teacher-recheck-form'].handlers.submit({preventDefault() {}});
    await tick();
    assert.equal(e['teacher-recheck-form'].hidden, true);
    assert.equal(e['teacher-recheck-toggle'].hidden, true);
    assert.ok(e['teacher-recheck-message'].textContent.includes('<script>not HTML</script>'));
    const count = ui.calls.length;
    e['teacher-recheck-form'].handlers.submit({preventDefault() {}});
    await tick();
    assert.equal(ui.calls.length, count);
    const already = await scenario({state: 'ok', requested: true, available: false, message: 'Уже запрошено'});
    assert.equal(already.elements['teacher-recheck-toggle'].hidden, true);
    console.log('OK: status, form, CSRF, retry, safe text, duplicate submission');
})().catch(error => { console.error(error); process.exitCode = 1; });
