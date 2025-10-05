const API = {
  listInstances: () => fetchJson('/ui/api/instances'),
  createInstance: (payload) =>
    fetchJson('/ui/api/instances', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  getSnapshot: (id) => fetchJson(`/ui/api/instances/${id}/snapshot`),
  stopInstance: (id) => fetchJson(`/ui/api/instances/${id}/stop`, { method: 'POST' }),
  problemSets: () => fetchJson('/ui/api/templates/problem-sets'),
  competitionDefaults: () => fetchJson('/ui/api/templates/competition-defaults'),
  defaultCompetitors: () => fetchJson('/ui/api/templates/default-competitors'),
};

const DEFAULT_REQUEST_FORMAT = {
  url: '/v1/chat/completions',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: 'Bearer {api_key}',
  },
  body_template: {
    messages: '{messages}',
    model: '{model_id}',
    temperature: 0.7,
  },
};

const DEFAULT_RESPONSE_FORMAT = {
  response_path: 'choices[0].message.content',
  error_path: 'error.message',
};

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

const state = {
  instances: [],
  selectedInstance: null,
  listPollingHandle: null,
  detailPollingHandle: null,
  competitionDefaults: null,
  defaultCompetitors: [],
  formBuilt: false,
};

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await loadDefaults();
  } catch (error) {
    console.warn('Failed to load competition defaults', error);
  }

  setupModal();
  setupToolbar();
  await loadProblemSets();
  await loadInstances();
  startAutoRefresh();
});

async function loadDefaults() {
  const [defaultsResult, competitorsResult] = await Promise.all([
    API.competitionDefaults(),
    API.defaultCompetitors(),
  ]);

  if (defaultsResult.status !== 'success') {
    throw new Error(defaultsResult.message || 'Unable to load defaults');
  }
  state.competitionDefaults = defaultsResult.data || {};

  if (competitorsResult.status === 'success' && Array.isArray(competitorsResult.data)) {
    state.defaultCompetitors = competitorsResult.data;
  } else {
    state.defaultCompetitors = [];
  }
}

function setupToolbar() {
  document.getElementById('create-instance').addEventListener('click', openModal);
  document.getElementById('refresh-instances').addEventListener('click', async () => {
    await loadInstances();
    await loadDetails();
  });
}

function setupModal() {
  const modal = document.getElementById('instance-modal');
  const form = document.getElementById('instance-form');
  const addCompetitorBtn = document.getElementById('add-competitor');
  const errorBox = document.getElementById('form-error');

  buildCompetitionForm();
  populateCompetitionForm(state.competitionDefaults);
  resetCompetitorsTable();

  document.querySelectorAll('[data-close]').forEach((button) => {
    button.addEventListener('click', () => modal.close());
  });

  modal.addEventListener('close', () => {
    form.reset();
    errorBox.textContent = '';
    populateCompetitionForm(state.competitionDefaults);
    resetCompetitorsTable();
  });

  addCompetitorBtn.addEventListener('click', addCompetitorRow);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.textContent = '';

    try {
      const payload = serializeForm(form);
      const result = await API.createInstance(payload);
      if (result.status !== 'success') {
        throw new Error(result.message || 'Failed to create competition');
      }
      modal.close();
      await loadInstances();
      selectInstance(result.data.id);
    } catch (error) {
      errorBox.textContent = error.message;
    }
  });
}

function openModal() {
  populateCompetitionForm(state.competitionDefaults);
  const modal = document.getElementById('instance-modal');
  modal.showModal();
}

function startAutoRefresh() {
  if (!state.listPollingHandle) {
    state.listPollingHandle = setInterval(loadInstances, 5000);
  }
}

async function loadProblemSets() {
  try {
    const result = await API.problemSets();
    if (result.status !== 'success') return;
    const select = document.getElementById('problem-set-select');
    select.innerHTML = '<option value="">-- Select template (optional) --</option>';
    result.data.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.path;
      option.textContent = `${item.name} (${item.count})`;
      select.appendChild(option);
    });
  } catch (error) {
    console.warn('Failed to load problem sets', error);
  }
}

async function loadInstances() {
  try {
    const result = await API.listInstances();
    if (result.status !== 'success') {
      throw new Error(result.message || 'Unable to list instances');
    }
    state.instances = result.data;
    renderInstanceList();
  } catch (error) {
    console.error(error);
  }
}

function renderInstanceList() {
  const container = document.getElementById('instance-container');
  container.innerHTML = '';
  container.classList.toggle('empty', state.instances.length === 0);

  state.instances.forEach((instance) => {
    const card = document.createElement('article');
    card.className = 'instance-card';
    card.dataset.id = instance.id;

    if (state.selectedInstance === instance.id) {
      card.classList.add('active');
    }

    const statusClass = {
      running: 'badge--running',
      completed: 'badge--success',
      failed: 'badge--error',
    }[instance.status] || '';

    const description = instance.description || instance.competition_config?.competition_description || 'No description';

    card.innerHTML = `
      <div class="instance-card__title">${escapeHtml(instance.title)}</div>
      <div class="instance-card__meta">
        <span class="badge ${statusClass}">${escapeHtml(instance.status)}</span>
        <span>Port ${instance.server_port}</span>
        <span>Created ${formatRelative(instance.created_at)}</span>
      </div>
      <div class="status-line">${escapeHtml(description)}</div>
    `;

    card.addEventListener('click', () => selectInstance(instance.id));

    container.appendChild(card);
  });

  if (state.selectedInstance && !state.instances.find((i) => i.id === state.selectedInstance)) {
    clearDetails();
  }
}

async function selectInstance(id) {
  state.selectedInstance = id;
  renderInstanceList();

  if (state.detailPollingHandle) {
    clearInterval(state.detailPollingHandle);
  }

  await loadDetails();
  state.detailPollingHandle = setInterval(loadDetails, 4000);
}

function clearDetails() {
  const container = document.querySelector('#details-container .panel__body');
  container.innerHTML = '<p>Select a competition to view details.</p>';
  container.classList.add('empty');
  state.selectedInstance = null;
  if (state.detailPollingHandle) {
    clearInterval(state.detailPollingHandle);
    state.detailPollingHandle = null;
  }
}

async function loadDetails() {
  if (!state.selectedInstance) return;

  try {
    const snapshotResult = await API.getSnapshot(state.selectedInstance);
    if (snapshotResult.status !== 'success') {
      throw new Error(snapshotResult.message || 'Unable to load details');
    }
    renderDetails(snapshotResult.data);
  } catch (error) {
    console.error(error);
  }
}

function renderDetails(snapshot) {
  const container = document.querySelector('#details-container');
  const body = container.querySelector('.panel__body');
  body.classList.remove('empty');
  body.innerHTML = '';

  body.appendChild(renderHeader(snapshot));
  body.appendChild(renderStats(snapshot));
  body.appendChild(renderConfigSummary(snapshot));
  body.appendChild(renderLeaderboard(snapshot));
  body.appendChild(renderParticipants(snapshot));
  body.appendChild(renderTimeline(snapshot));
}

function renderHeader(snapshot) {
  const wrapper = element('div', { class: 'details__header' });

  const title = element('div');
  title.innerHTML = `
    <h3 class="details__title">${escapeHtml(snapshot.title)}</h3>
    <div class="details__meta">
      <span>Instance ID: <code>${snapshot.id}</code></span>
      <span>Port: <code>${snapshot.server_port}</code></span>
      <span>Status: <strong>${escapeHtml(snapshot.status)}</strong></span>
    </div>
  `;

  if (snapshot.last_error) {
    const errorNote = element('p', { class: 'status-line' }, `Last error: ${snapshot.last_error}`);
    errorNote.style.color = '#f87171';
    title.appendChild(errorNote);
  }

  const actions = element('div', { class: 'details__actions' });
  const refreshBtn = element('button', { class: 'button' }, 'Refresh now');
  const stopBtn = element('button', { class: 'button button--ghost' }, 'Terminate');

  refreshBtn.addEventListener('click', loadDetails);
  stopBtn.addEventListener('click', async () => {
    if (!confirm('Terminate server and judge for this competition?')) return;
    await API.stopInstance(snapshot.id);
    await loadInstances();
    await loadDetails();
  });

  actions.append(refreshBtn, stopBtn);
  wrapper.append(title, actions);
  return wrapper;
}

function renderStats(snapshot) {
  const runtime = snapshot.runtime || {};
  const competitors = snapshot.competitors || [];
  const config = snapshot.competition_config || {};

  const grid = element('div', { class: 'stats-grid' });
  grid.appendChild(statCard('Competitors', competitors.length));
  grid.appendChild(statCard('Problems', snapshot.problem_ids.length));
  grid.appendChild(statCard('Status', snapshot.status));
  if (snapshot.competition_id) {
    grid.appendChild(statCard('Competition ID', snapshot.competition_id));
  }
  if (config.max_tokens_per_participant !== undefined) {
    grid.appendChild(statCard('Token Limit', config.max_tokens_per_participant));
  }
  if (runtime.rankings && runtime.rankings.status === 'success') {
    const leader = runtime.rankings.data?.[0];
    if (leader) {
      grid.appendChild(
        statCard('Current Leader', leader.name || leader.participant_name || leader.id || 'N/A'),
      );
    }
  }
  if (snapshot.oj_endpoint) {
    grid.appendChild(statCard('OJ Endpoint', snapshot.oj_endpoint));
  }

  return grid;
}

function renderConfigSummary(snapshot) {
  const config = snapshot.competition_config || {};
  const rules = config.rules || {};

  const container = element('div');
  container.innerHTML = '<h4>Key Parameters</h4>';

  const list = element('div', { class: 'timeline' });
  const scoring = rules.scoring || {};
  list.appendChild(
    summaryItem('Scoring', `Bronze ${scoring.bronze}, Silver ${scoring.silver}, Gold ${scoring.gold}, Platinum ${scoring.platinum}`),
  );
  list.appendChild(
    summaryItem('Bonus for First AC', rules.bonus_for_first_ac ?? '0'),
  );
  list.appendChild(summaryItem('Lambda', rules.lambda ?? '—'));
  list.appendChild(
    summaryItem(
      'Error Propagation',
      rules.error_propagation?.enabled ? 'Enabled' : 'Disabled',
    ),
  );

  container.appendChild(list);
  return container;
}

function summaryItem(label, value) {
  const item = element('div', { class: 'timeline-item' });
  const header = element('div', { class: 'timeline-item__header' });
  header.innerHTML = `<span>${escapeHtml(label)}</span>`;
  const body = element('div', { class: 'timeline-item__body' });
  body.textContent = value;
  item.append(header, body);
  return item;
}

function renderLeaderboard(snapshot) {
  const runtime = snapshot.runtime || {};
  const container = element('div');
  container.innerHTML = '<h4>Leaderboard</h4>';

  const payload = runtime.rankings;
  if (!payload || payload.status !== 'success' || !Array.isArray(payload.data)) {
    const message = element(
      'p',
      { class: 'status-line' },
      'Leaderboard will appear once the competition is underway.',
    );
    container.appendChild(message);
    return container;
  }

  const tableWrap = element('div', { class: 'table-scroll' });
  const table = element('table', { class: 'table' });
  table.innerHTML = `
    <thead>
      <tr>
        <th>Rank</th>
        <th>Name</th>
        <th>Score</th>
        <th>Solved</th>
        <th>Tokens Used</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector('tbody');
  payload.data.forEach((row, index) => {
    const score =
      row.problem_pass_score ??
      (row.score ?? row.total_score ?? '—');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td>${escapeHtml(row.name || row.participant_name || row.id)}</td>
      <td>${score}</td>
      <td>${Array.isArray(row.solved_problems) ? row.solved_problems.length : row.problem_solved ?? '—'}</td>
      <td>${row.tokens_used ?? row.LLM_tokens ?? '—'}</td>
      <td>${row.is_running === false ? 'Terminated' : 'Running'}</td>
    `;
    tbody.appendChild(tr);
  });

  tableWrap.appendChild(table);
  container.appendChild(tableWrap);
  return container;
}

function renderParticipants(snapshot) {
  const runtime = snapshot.runtime || {};
  const payload = runtime.participants;

  const container = element('div');
  container.innerHTML = '<h4>Participants</h4>';

  if (!payload || payload.status !== 'success' || !Array.isArray(payload.data)) {
    container.appendChild(
      element('p', { class: 'status-line' }, 'Participant information will load after registration.'),
    );
    return container;
  }

  const list = element('div', { class: 'timeline' });
  payload.data.forEach((participant) => {
    const item = element('div', { class: 'timeline-item' });
    const header = element('div', { class: 'timeline-item__header' });
    header.innerHTML = `
      <span>${escapeHtml(participant.name || participant.id)}</span>
      <span>${participant.is_running ? 'Running' : 'Terminated'}</span>
    `;

    const body = element('div', { class: 'timeline-item__body' });
    body.innerHTML = `
      <div>Score: ${participant.problem_pass_score ?? participant.score ?? '—'} | Tokens: ${participant.LLM_tokens ?? '—'} | Remaining: ${participant.remaining_tokens ?? '—'}</div>
      <div>Solved problems: ${(participant.solved_problems || []).map((p) => p.problem_id || p).join(', ') || 'None yet'}</div>
      ${participant.termination_reason ? `<div>Termination Reason: ${escapeHtml(participant.termination_reason)}</div>` : ''}
    `;

    item.append(header, body);
    list.appendChild(item);
  });

  container.appendChild(list);
  return container;
}

function renderTimeline(snapshot) {
  const runtime = snapshot.runtime || {};
  const payload = runtime.submissions;
  const container = element('div');
  container.innerHTML = '<h4>Recent Actions</h4>';

  if (!payload || payload.status !== 'success' || !Array.isArray(payload.data) || payload.data.length === 0) {
    container.appendChild(element('p', { class: 'status-line' }, 'No submissions recorded yet.'));
    return container;
  }

  const list = element('div', { class: 'timeline' });
  payload.data
    .slice()
    .sort((a, b) => new Date(b.submitted_at) - new Date(a.submitted_at))
    .slice(0, 20)
    .forEach((submission) => {
      const item = element('div', { class: 'timeline-item' });
      const header = element('div', { class: 'timeline-item__header' });
      header.innerHTML = `
        <span>${escapeHtml(submission.participant_name || submission.participant_id)}</span>
        <span>${new Date(submission.submitted_at).toLocaleString()}</span>
      `;

      const body = element('div', { class: 'timeline-item__body' });
      body.innerHTML = `
        <div>Problem: <code>${escapeHtml(submission.problem_id || '—')}</code></div>
        <div>Status: <strong>${escapeHtml(submission.status || 'unknown')}</strong></div>
        <div>Language: ${escapeHtml(submission.language || 'unknown')} | Tokens: ${submission.token_cost ?? '—'}</div>
      `;

      item.append(header, body);
      list.appendChild(item);
    });

  container.appendChild(list);
  return container;
}

function buildCompetitionForm() {
  if (state.formBuilt) return;
  const defaults = state.competitionDefaults || {};

  const general = document.getElementById('competition-general-fields');
  createField(general, {
    label: 'Title',
    path: 'competition_title',
    type: 'text',
    placeholder: 'e.g., Bronze Sprint',
    required: true,
  });
  createField(general, {
    label: 'Description',
    path: 'competition_description',
    type: 'text',
    placeholder: 'Optional context for this run',
  });
  createField(general, {
    label: 'Maximum Tokens per Competitor',
    path: 'max_tokens_per_participant',
    type: 'number',
    min: 1,
    step: 1,
  });

  const apiConfig = document.getElementById('api-config-fields');
  createField(apiConfig, {
    label: 'API Retry Attempts',
    path: 'api_config.max_retries',
    type: 'number',
    min: 0,
    step: 1,
  });
  createField(apiConfig, {
    label: 'Retry Delay (seconds)',
    path: 'api_config.retry_delay',
    type: 'number',
    min: 0,
    step: 1,
  });

  const logConfig = document.getElementById('log-config-fields');
  createField(logConfig, {
    label: 'Log Level',
    path: 'log.level',
    type: 'text',
  });
  createField(logConfig, {
    label: 'Log Directory',
    path: 'log.dir',
    type: 'text',
  });
  createField(logConfig, {
    label: 'Enable ANSI Colors',
    path: 'log.enable_colors',
    type: 'checkbox',
  });

  const scoring = document.getElementById('scoring-fields');
  const scoringDefaults = defaults.rules?.scoring || {};
  Object.keys(scoringDefaults).forEach((tier) => {
    createField(scoring, {
      label: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} Score`,
      path: `rules.scoring.${tier}`,
      type: 'number',
      step: 1,
    });
  });
  createField(scoring, {
    label: 'Bonus for First AC',
    path: 'rules.bonus_for_first_ac',
    type: 'number',
    step: 1,
  });
  createField(scoring, {
    label: 'Lambda',
    path: 'rules.lambda',
    type: 'number',
    step: 1,
  });

  const propagation = document.getElementById('propagation-fields');
  createField(propagation, {
    label: 'Enable Error Propagation',
    path: 'rules.error_propagation.enabled',
    type: 'checkbox',
  });
  createField(propagation, {
    label: 'Error Propagation Description',
    path: 'rules.error_propagation.description',
    type: 'text',
    placeholder: 'What happens when a participant fails',
  });

  const penalties = document.getElementById('penalties-fields');
  const penaltyKeys = Object.keys(defaults.rules?.penalties || {});
  penaltyKeys.forEach((code) => {
    createField(penalties, {
      label: `Penalty (${code})`,
      path: `rules.penalties.${code}`,
      type: 'number',
      step: 1,
    });
  });

  const submissionCosts = document.getElementById('submission-fields');
  const submissionKeys = Object.keys(defaults.rules?.submission_tokens || {});
  submissionKeys.forEach((code) => {
    createField(submissionCosts, {
      label: `Submission Tokens (${code})`,
      path: `rules.submission_tokens.${code}`,
      type: 'number',
      step: 1,
    });
  });

  const hintFields = document.getElementById('hint-fields');
  const hintLevels = Object.keys(defaults.rules?.hint_tokens || {});
  hintLevels.forEach((level) => {
    createField(hintFields, {
      label: `Hint Tokens (${level})`,
      path: `rules.hint_tokens.${level}`,
      type: 'number',
      step: 1,
    });
  });

  const testTokens = document.getElementById('test-token-fields');
  createField(testTokens, {
    label: 'Test Token Base Cost',
    path: 'rules.test_tokens.default',
    type: 'number',
    step: 1,
  });
  createField(testTokens, {
    label: 'Per-Test-Case Additional Cost',
    path: 'rules.test_tokens.per_test_case',
    type: 'number',
    step: 1,
  });

  document.querySelectorAll('[data-add-language]').forEach((button) => {
    button.addEventListener('click', () => addMultiplierRow(button.dataset.addLanguage));
  });

  state.formBuilt = true;
}

function createField(container, { label, path, type = 'number', placeholder = '', min, step, required = false }) {
  const wrapper = document.createElement('label');
  if (type === 'checkbox') {
    wrapper.classList.add('checkbox');
  }

  const labelText = document.createElement('span');
  labelText.textContent = label;

  let input;
  if (type === 'textarea') {
    input = document.createElement('textarea');
    input.rows = 2;
  } else {
    input = document.createElement('input');
    input.type = type === 'checkbox' ? 'checkbox' : type;
  }

  if (placeholder && type !== 'checkbox') {
    input.placeholder = placeholder;
  }
  if (min !== undefined) {
    input.min = min;
  }
  if (step !== undefined && type !== 'checkbox') {
    input.step = step;
  }
  if (required) {
    input.required = true;
  }

  input.dataset.configPath = path;
  if (type === 'checkbox') {
    wrapper.appendChild(input);
    wrapper.appendChild(labelText);
  } else {
    wrapper.appendChild(labelText);
    wrapper.appendChild(input);
  }
  container.appendChild(wrapper);
  return input;
}

function populateCompetitionForm(config = {}) {
  const defaults = config || state.competitionDefaults || {};
  document.querySelectorAll('[data-config-path]').forEach((input) => {
    const path = input.dataset.configPath;
    const value = getValueByPath(defaults, path);

    if (input.type === 'checkbox') {
      input.checked = Boolean(value);
    } else if (input.tagName === 'TEXTAREA') {
      input.value = value ?? '';
    } else if (input.type === 'number') {
      input.value = value !== undefined && value !== null ? value : '';
    } else {
      input.value = value ?? '';
    }
  });

  setMultiplierRows('test', getValueByPath(defaults, MULTIPLIER_CONFIG.test.path));
  setMultiplierRows('input', getValueByPath(defaults, MULTIPLIER_CONFIG.input.path));
  setMultiplierRows('output', getValueByPath(defaults, MULTIPLIER_CONFIG.output.path));
}

function resetCompetitorsTable() {
  setCompetitorRows(state.defaultCompetitors);
}

const MULTIPLIER_CONFIG = {
  test: { bodyId: 'test-multipliers-body', path: 'rules.test_tokens.language_multipliers' },
  input: { bodyId: 'input-multipliers-body', path: 'rules.input_token_multipliers' },
  output: { bodyId: 'output-multipliers-body', path: 'rules.output_token_multipliers' },
};

function setCompetitorRows(list) {
  const tbody = document.querySelector('#competitor-table tbody');
  tbody.innerHTML = '';

  if (Array.isArray(list) && list.length) {
    list.forEach((spec) => addCompetitorRow(spec));
  } else {
    addCompetitorRow();
  }
}

function setMultiplierRows(type, data) {
  const config = MULTIPLIER_CONFIG[type];
  const tbody = document.getElementById(config.bodyId);
  tbody.innerHTML = '';

  const entries = Object.entries(data || {});
  if (!entries.length) {
    addMultiplierRow(type);
    return;
  }

  entries.forEach(([name, value]) => addMultiplierRow(type, name, value));
}

function addMultiplierRow(type, name = '', value = '') {
  const config = MULTIPLIER_CONFIG[type];
  const tbody = document.getElementById(config.bodyId);
  const template = document.getElementById('language-row-template');
  const row = template.content.firstElementChild.cloneNode(true);
  const [nameInput, valueInput] = row.querySelectorAll('input');
  nameInput.value = name;
  valueInput.value = value;
  valueInput.step = '0.01';

  const removeButton = row.querySelector('[data-action="remove-multiplier"]');
  removeButton?.addEventListener('click', () => {
    if (tbody.children.length > 1) {
      row.remove();
    }
  });

  tbody.appendChild(row);
}

function collectMultiplierValues(type) {
  const config = MULTIPLIER_CONFIG[type];
  const tbody = document.getElementById(config.bodyId);
  const values = {};

  Array.from(tbody.querySelectorAll('tr')).forEach((row) => {
    const nameInput = row.querySelector('input[data-field="name"]');
    const valueInput = row.querySelector('input[data-field="value"]');
    const name = nameInput.value.trim();
    const raw = valueInput.value.trim();
    if (!name) return;
    const numeric = raw === '' ? NaN : parseFloat(raw);
    values[name] = Number.isNaN(numeric) ? 0 : numeric;
  });

  return values;
}

function addCompetitorRow(spec = {}) {
  const tbody = document.querySelector('#competitor-table tbody');
  const template = document.getElementById('competitor-row-template');
  const row = template.content.firstElementChild.cloneNode(true);

  const extras = { ...spec };
  const nameInput = row.querySelector('input[name="name"]');
  const modelInput = row.querySelector('input[name="model_id"]');
  const baseInput = row.querySelector('input[name="api_base_url"]');
  const keyInput = row.querySelector('input[name="api_key"]');
  const promptInput = row.querySelector('input[name="prompt_config_path"]');
  const limitInput = row.querySelector('input[name="limit_tokens"]');

  const name = extras.name ?? '';
  const modelId = extras.model_id ?? '';
  const apiBase = extras.api_base_url ?? '';
  const apiKey = extras.api_key ?? '';
  const prompt = extras.prompt_config_path ?? '';
  const limitTokens = extras.limit_tokens ?? '';

  if (nameInput) nameInput.value = name;
  if (modelInput) modelInput.value = modelId;
  if (baseInput) baseInput.value = apiBase;
  if (keyInput) keyInput.value = apiKey;
  if (promptInput) promptInput.value = prompt;
  if (limitInput) limitInput.value = limitTokens;

  delete extras.name;
  delete extras.model_id;
  delete extras.api_base_url;
  delete extras.api_key;
  delete extras.prompt_config_path;
  delete extras.limit_tokens;

  if (!extras.type) {
    extras.type = 'generic';
  }
  if (!extras.request_format) {
    extras.request_format = deepClone(DEFAULT_REQUEST_FORMAT);
  }
  if (!extras.response_format) {
    extras.response_format = deepClone(DEFAULT_RESPONSE_FORMAT);
  }

  row.dataset.extra = JSON.stringify(extras);

  const removeButton = row.querySelector('[data-action="remove-competitor"]');
  removeButton?.addEventListener('click', () => {
    row.remove();
    if (tbody.children.length === 0) {
      addCompetitorRow();
    }
  });

  tbody.appendChild(row);
}

function serializeForm(form) {
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  const ids = (payload.problem_ids || '')
    .split(/\s|,/) // newline or comma
    .map((value) => value.trim())
    .filter(Boolean);

  const competitors = Array.from(document.querySelectorAll('#competitor-table tbody tr'))
    .map((row) => {
      const extra = parseJsonSafe(row.dataset.extra) || {};
      const data = { ...extra };
      row.querySelectorAll('input').forEach((input) => {
        if (!input.name) return;
        const raw = input.value.trim();
        if (raw === '') {
          delete data[input.name];
          return;
        }
        data[input.name] = input.type === 'number' ? Number(raw) : raw;
      });
      if (!data.type) {
        data.type = 'generic';
      }
      return data;
    })
    .filter((entry) => Object.keys(entry).length);

  if (!competitors.length) {
    throw new Error('Please configure at least one competitor.');
  }

  const competitionConfig = collectCompetitionConfig();
  const competitionTitle = competitionConfig.competition_title || payload.title || 'Untitled Competition';
  const competitionDescription = competitionConfig.competition_description || payload.description || '';

  return {
    title: competitionTitle,
    description: competitionDescription,
    competition_config: competitionConfig,
    problem_set_file: payload.problem_set_file || undefined,
    problem_ids: ids,
    server_port: payload.server_port ? Number(payload.server_port) : undefined,
    oj_port: payload.oj_port ? Number(payload.oj_port) : undefined,
    oj_endpoint: payload.oj_endpoint || undefined,
    start_oj: formData.get('start_oj') === 'on',
    competitors,
  };
}

function collectCompetitionConfig() {
  const defaults = state.competitionDefaults || {};
  const config = deepClone(defaults);

  document.querySelectorAll('[data-config-path]').forEach((input) => {
    const path = input.dataset.configPath;
    const defaultValue = getValueByPath(defaults, path);
    const value = coerceInputValue(input, defaultValue);
    setValueByPath(config, path, value);
  });

  setValueByPath(config, MULTIPLIER_CONFIG.test.path, collectMultiplierValues('test'));
  setValueByPath(config, MULTIPLIER_CONFIG.input.path, collectMultiplierValues('input'));
  setValueByPath(config, MULTIPLIER_CONFIG.output.path, collectMultiplierValues('output'));

  return config;
}

function coerceInputValue(input, defaultValue) {
  if (input.type === 'checkbox') {
    return input.checked;
  }

  const raw = input.value.trim();
  if (raw === '') {
    return defaultValue;
  }

  if (input.type === 'number') {
    const numeric = raw.includes('.') ? parseFloat(raw) : parseInt(raw, 10);
    if (Number.isNaN(numeric)) {
      return defaultValue;
    }
    if (typeof defaultValue === 'number' && Number.isInteger(defaultValue)) {
      return Math.round(numeric);
    }
    return numeric;
  }

  return raw;
}

function deepClone(value) {
  if (typeof structuredClone === 'function') {
    return structuredClone(value || {});
  }
  return JSON.parse(JSON.stringify(value || {}));
}

function parseJsonSafe(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (error) {
    console.warn('Failed to parse JSON', error);
    return null;
  }
}

function getValueByPath(obj, path) {
  if (!path) return undefined;
  return path.split('.').reduce((acc, key) => (acc && key in acc ? acc[key] : undefined), obj);
}

function setValueByPath(obj, path, value) {
  const parts = path.split('.');
  let current = obj;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) {
      current[part] = value;
      return;
    }
    if (!(part in current) || typeof current[part] !== 'object' || current[part] === null) {
      current[part] = {};
    }
    current = current[part];
  });
}

function statCard(label, value) {
  const card = element('div', { class: 'stat-card' });
  const labelEl = element('div', { class: 'stat-card__label' }, label);
  const valueEl = element('div', { class: 'stat-card__value' }, String(value ?? '—'));
  card.append(labelEl, valueEl);
  return card;
}

function element(tag, attrs = {}, text) {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    el.setAttribute(key, value);
  });
  if (text !== undefined) {
    el.textContent = text;
  }
  return el;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

function formatRelative(timestamp) {
  if (!timestamp) return 'unknown';
  const date = new Date(timestamp);
  const diff = Date.now() - date.getTime();
  if (Number.isNaN(diff)) return 'unknown';
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes === 1) return '1 minute ago';
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours === 1) return '1 hour ago';
  if (hours < 24) return `${hours} hours ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}
