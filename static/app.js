async function summarize() {
    const fileInput = document.getElementById('fileInput');
    const reqFormat = document.getElementById('reqFormat').value;
    const whyJoinFormat = document.getElementById('whyJoinFormat').value;
    const submitBtn = document.getElementById('submitBtn');
    const loading = document.getElementById('loading');
    const error = document.getElementById('error');
    const result = document.getElementById('result');

    // Validate
    if (!fileInput.files || !fileInput.files[0]) {
        showError('Please select a file first.');
        return;
    }

    // Clear previous
    hideError();
    result.classList.add('hidden');
    loading.classList.remove('hidden');
    submitBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('req_format', reqFormat);
    formData.append('why_join_format', whyJoinFormat);

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const responseText = await res.text();
        let data;

        try {
            data = responseText ? JSON.parse(responseText) : {};
        } catch (_) {
            data = {};
        }

        if (!res.ok) {
            showError(data.detail || data.error || responseText || `Request failed (${res.status}).`);
            return;
        }

        if (!data.formatted_text) {
            showError('The server returned an invalid result.');
            return;
        }

        document.getElementById('resultText').textContent = data.formatted_text;
        renderResult(data.data, reqFormat);
        result.classList.remove('hidden');

    } catch (err) {
        showError('An error occurred: ' + err.message);
    } finally {
        loading.classList.add('hidden');
        submitBtn.disabled = false;
    }
}

function showError(msg) {
    const el = document.getElementById('error');
    el.textContent = msg;
    el.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error').classList.add('hidden');
}

function copyResult() {
    const text = document.getElementById('resultText').textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.querySelector('#result button');
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = orig, 2000);
    });
}

function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function renderList(container, items) {
    const list = createElement('ul', 'list-disc pl-5 space-y-1');
    (items.length ? items : ['N/A']).forEach(item => {
        list.appendChild(createElement('li', '', item));
    });
    container.appendChild(list);
}

function renderResult(data, requirementFormat) {
    const view = document.getElementById('resultView');
    view.replaceChildren();

    view.appendChild(createElement('h3', 'text-xl font-bold text-gray-900', data.job_title || 'N/A'));
    if (data.subtitle) {
        view.appendChild(createElement('p', 'text-gray-500 mt-1', data.subtitle));
    }

    const basicInfo = [data.employment_type, data.contract_type, data.location]
        .map(value => value || 'N/A')
        .join(' | ');
    view.appendChild(createElement('p', 'font-medium mt-4', basicInfo));
    view.appendChild(createElement('p', 'mt-1', data.salary || 'N/A'));
    if (data.bounty) view.appendChild(createElement('p', 'mt-1', data.bounty));
    if (data.short_description) {
        view.appendChild(createElement('p', 'mt-4 leading-relaxed', data.short_description));
    }

    view.appendChild(createElement('h4', 'font-semibold text-gray-900 mt-5 mb-2', 'Requirements'));
    if (requirementFormat === 'tag' && data.requirements.length) {
        const tags = createElement('div', 'flex flex-wrap gap-2');
        data.requirements.forEach(requirement => {
            tags.appendChild(createElement(
                'span',
                'requirement-tag inline-flex rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800',
                requirement
            ));
        });
        view.appendChild(tags);
    } else {
        renderList(view, data.requirements);
    }

    view.appendChild(createElement('h4', 'font-semibold text-gray-900 mt-5 mb-2', 'Why Join?'));
    renderList(view, data.why_join);
}
