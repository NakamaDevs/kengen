/* Kengen's read-only viewer. Credentials remain in memory and never enter examples. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {key: '', stores: [], store: null, storeToken: '', models: [], modelToken: '',
    tokens: [''], page: 0, next: '', filters: {}, request: null, busy: false, generation: 0, controller: null};
  const json = value => JSON.stringify(value, null, 2);
  const shellQuote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
  function busy(value) {
    state.busy = value;
    document.querySelectorAll('main button, main input, main select, #stores button, #more-stores').forEach(el => { el.disabled = value; });
    $('previous').disabled = value || !state.store || state.page === 0;
    $('next').disabled = value || !state.next;
    $('query-form').querySelectorAll('input,button').forEach(el => { el.disabled = value || !state.store; });
    $('models-tab').disabled = value || !state.store;
  }
  async function action(work) {
    if (state.busy) return;
    const generation = state.generation;
    busy(true); notice();
    try { await work(); }
    catch (error) {
      if (generation === state.generation && error.name !== 'AbortError') notice(error.message);
    } finally { if (generation === state.generation) busy(false); }
  }
  async function api(method, path, body, grpcMethod, grpcBody) {
    const generation = state.generation;
    state.controller = new AbortController();
    const timer = setTimeout(() => state.controller?.abort(), 20000);
    state.request = {method, path, body, grpcMethod, grpcBody};
    renderExample();
    $('response').textContent = 'Loading…'; $('response-status').textContent = '';
    let response;
    try {
      response = await fetch(path, {method, headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + state.key},
        body: body ? JSON.stringify(body) : undefined, signal: state.controller.signal, cache: 'no-store', redirect: 'error'});
      const data = await response.json();
      if (generation !== state.generation) throw new DOMException('Disconnected', 'AbortError');
      $('response').textContent = json(data);
      $('response-status').textContent = String(response.status);
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          disconnect();
          notice('Access was rejected. Connect with a valid Kengen API key.');
          throw new DOMException('Access rejected', 'AbortError');
        }
        throw new Error(data.message || 'The API request failed (' + response.status + ').');
      }
      return data;
    } catch (error) {
      if (generation !== state.generation) throw new DOMException('Disconnected', 'AbortError');
      if (error.name === 'AbortError') throw new Error('The request timed out. Try again.');
      if (!response) throw new Error('Cannot reach Kengen. Check your connection and try again.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function renderExample() {
    const r = state.request;
    if (!r) { $('request').textContent = ''; return; }
    const format = $('example-format').value;
    const body = r.body ? '\n\n' + json(r.body) : '';
    $('grpc-note').hidden = format !== 'grpc';
    if (format === 'http') {
      $('request').textContent = r.method + ' ' + r.path + ' HTTP/1.1\nHost: ' + location.host + '\nAuthorization: Bearer <FGA_API_TOKEN>\nContent-Type: application/json' + body;
    } else if (format === 'curl') {
      $('request').textContent = 'curl --request ' + r.method + ' ' + shellQuote(location.origin + r.path) + ' \\\n  --header "Authorization: Bearer $FGA_API_TOKEN" \\\n  --header \'Content-Type: application/json\'' + (r.body ? ' \\\n  --data ' + shellQuote(JSON.stringify(r.body)) : '');
    } else {
      $('request').textContent = 'grpcurl -plaintext -H "Authorization: Bearer $FGA_API_TOKEN" \\\n  -d ' + shellQuote(json(r.grpcBody)) + ' \\\n  "$FGA_GRPC_ADDR" openfga.v1.OpenFGAService/' + r.grpcMethod;
    }
  }
  function renderStores() {
    $('stores').replaceChildren();
    for (const store of state.stores) {
      const button = document.createElement('button'); button.className = 'store';
      button.setAttribute('aria-current', String(store.id === state.store?.id));
      button.append(document.createTextNode(store.name || 'Unnamed store'));
      const id = document.createElement('small'); id.textContent = store.id; button.append(id);
      button.addEventListener('click', () => action(() => selectStore(store)));
      $('stores').append(button);
    }
    $('store-count').textContent = state.stores.length + (state.storeToken ? '+' : '');
    $('more-stores').hidden = !state.storeToken;
    $('stores-hint').textContent = state.stores.length ? '' : 'No stores found. Create one through the API.';
  }
  async function loadStores(continuation = '') {
    const query = new URLSearchParams({page_size: '50'});
    if (continuation) query.set('continuation_token', continuation);
    const data = await api('GET', '/stores?' + query, null, 'ListStores', {page_size: 50, ...(continuation ? {continuation_token: continuation} : {})});
    state.stores.push(...(data.stores || [])); state.storeToken = data.continuation_token || '';
    renderStores();
  }
  function tab(name) {
    for (const current of ['tuples', 'models']) {
      $(current + '-panel').hidden = current !== name;
      $(current + '-tab').setAttribute('aria-selected', String(current === name));
    }
  }
  async function selectStore(store) {
    state.store = store; state.models = []; state.modelToken = ''; state.filters = {};
    state.tokens = ['']; state.page = 0; state.next = '';
    $('query-form').reset(); $('model-select').replaceChildren(); $('model-json').textContent = '';
    $('model-summary').textContent = ''; $('model-visual').replaceChildren(); $('more-models').hidden = true;
    $('store-name').textContent = store.name || 'Unnamed store'; $('store-id').textContent = store.id;
    renderStores(); tab('tuples');
    await readTuples(0);
  }
  async function readTuples(page) {
    if (!state.store) return;
    const continuation = state.tokens[page] || '';
    const body = {page_size: 50, ...(Object.keys(state.filters).length ? {tuple_key: state.filters} : {}),
      ...(continuation ? {continuation_token: continuation} : {})};
    $('tuples').replaceChildren(); $('empty').hidden = false;
    $('empty').textContent = 'Loading tuples…'; $('page-summary').textContent = '';
    let data;
    try {
      data = await api('POST', '/stores/' + encodeURIComponent(state.store.id) + '/read', body, 'Read', {store_id: state.store.id, ...body});
    } catch (error) {
      $('empty').textContent = 'The query did not complete. Check the message above and try again.';
      throw error;
    }
    state.page = page; state.next = data.continuation_token || '';
    const tuples = data.tuples || [];
    $('tuples').replaceChildren();
    for (const tuple of tuples) {
      const row = document.createElement('tr');
      for (const [index, value] of [tuple.key.user, tuple.key.relation, tuple.key.object, tuple.key.condition?.name || '—'].entries()) {
        const cell = document.createElement('td');
        if (index === 1) { const badge = document.createElement('span'); badge.className = 'relation'; badge.textContent = value; cell.append(badge); }
        else cell.textContent = value;
        if (index === 3 && tuple.key.condition) cell.title = json(tuple.key.condition);
        row.append(cell);
      }
      $('tuples').append(row);
    }
    $('empty').hidden = tuples.length > 0;
    $('empty').textContent = 'No tuples match this query.';
    $('page-summary').textContent = tuples.length + ' tuples · Page ' + (page + 1);
  }
  async function queryTuples() {
    const filters = {};
    for (const field of ['user', 'relation', 'object']) {
      const value = $('filter-' + field).value.trim(); if (value) filters[field] = value;
    }
    if (Object.keys(filters).length) {
      const object = filters.object || '', colon = object.indexOf(':');
      if (colon < 1 || (!object.slice(colon + 1) && !filters.user)) {
        throw new Error('Use a full object such as document:readme, or an object type such as document: together with a user.');
      }
    }
    state.filters = filters; state.tokens = ['']; state.page = 0; state.next = '';
    await readTuples(0);
  }
  async function loadModels(continuation = '') {
    const query = new URLSearchParams({page_size: '50'});
    if (continuation) query.set('continuation_token', continuation);
    const data = await api('GET', '/stores/' + encodeURIComponent(state.store.id) + '/authorization-models?' + query,
      null, 'ReadAuthorizationModels', {store_id: state.store.id, page_size: 50, ...(continuation ? {continuation_token: continuation} : {})});
    state.models.push(...(data.authorization_models || [])); state.modelToken = data.continuation_token || '';
    for (const model of data.authorization_models || []) {
      const option = document.createElement('option'); option.value = model.id; option.textContent = model.id;
      $('model-select').append(option);
    }
    $('more-models').hidden = !state.modelToken;
    showModel();
  }
  function showModel() {
    const model = state.models.find(item => item.id === $('model-select').value);
    KengenModel.render($('model-visual'), model);
    $('model-json').textContent = model ? json(model) : 'No authorization models in this store.';
    $('model-summary').textContent = model ? 'Schema ' + model.schema_version + ' · ' + (model.type_definitions || []).length + ' types' : '';
  }
  function disconnect() {
    state.generation++; state.controller?.abort(); state.key = ''; state.store = null;
    state.stores = []; state.models = []; state.tokens = ['']; state.next = ''; state.storeToken = ''; state.modelToken = ''; state.request = null;
    $('api-key').value = ''; $('login').hidden = false; $('workspace').hidden = true; $('disconnect').hidden = true;
    $('connection').textContent = 'Not connected'; $('connection').className = 'status';
    for (const id of ['tuples', 'model-select', 'model-visual']) $(id).replaceChildren();
    for (const id of ['response', 'request', 'model-json', 'store-id', 'store-name']) $(id).textContent = '';
    renderStores(); $('stores-hint').textContent = 'Connect to browse your stores.'; notice(); busy(false);
  }
  $('connect-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
    state.key = $('api-key').value.trim(); $('api-key').value = '';
    if (!state.key) throw new Error('Enter a Kengen API key.');
    state.stores = []; await loadStores();
    $('login').hidden = true; $('workspace').hidden = false; $('disconnect').hidden = false;
    $('connection').textContent = '● Connected'; $('connection').className = 'status connected';
    $('store-name').textContent = 'No stores';
    if (state.stores.length) await selectStore(state.stores[0]);
    else notice('This Kengen instance has no stores yet. Use the API to create one.');
  }); });
  $('disconnect').addEventListener('click', disconnect);
  $('more-stores').addEventListener('click', () => action(() => loadStores(state.storeToken)));
  $('query-form').addEventListener('submit', event => { event.preventDefault(); action(queryTuples); });
  $('clear-filters').addEventListener('click', () => action(async () => { $('query-form').reset(); await queryTuples(); }));
  $('next').addEventListener('click', () => action(async () => { state.tokens[state.page + 1] = state.next; await readTuples(state.page + 1); }));
  $('previous').addEventListener('click', () => action(() => readTuples(state.page - 1)));
  $('tuples-tab').addEventListener('click', () => action(async () => { tab('tuples'); await readTuples(state.page); }));
  $('models-tab').addEventListener('click', () => action(async () => { tab('models'); state.models = []; $('model-select').replaceChildren(); $('model-visual').replaceChildren(); $('model-json').textContent = ''; await loadModels(); }));
  $('more-models').addEventListener('click', () => action(() => loadModels(state.modelToken)));
  $('model-select').addEventListener('change', showModel);
  $('example-format').addEventListener('change', renderExample);
  $('copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('request').textContent); notice('Request example copied.'); } catch { notice('Select and copy the request example below.'); } });
})();
