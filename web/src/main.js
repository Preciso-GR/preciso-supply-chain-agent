import './style.css'

const app = document.querySelector('#app')
const STORAGE_KEY = 'supply-center-conversation-v2'
const RAW_EXTRACTION_KEY = 'supply-center-last-raw-extraction-v1'

const emptyPayload = () => ({
  document_id: '',
  snapshot_effective_date: new Date().toISOString().slice(0, 10),
  chunks: [],
  entities: [],
  relationships: [],
})

const escapeHTML = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;')

const fileName = (path) => String(path || 'source').split('/').at(-1)
const relationshipType = (edge) => String(edge?.keywords || '').split(',')[0].trim().toUpperCase() || 'EDGE'
const sentenceCase = (value) => String(value || '').replaceAll('-', ' ').replaceAll('_', ' ')

function displayName(id) {
  if (!id) return 'Unknown'
  return sentenceCase(String(id).split(':').at(-1))
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function loadConversation() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(saved) ? saved.slice(-30) : []
  } catch {
    return []
  }
}

function persistConversation() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.messages.slice(-30)))
}

function allPaths(result) {
  return (result?.potentially_exposed_products || []).flatMap((product) => product.paths || [])
}

function selectedPathEvidence() {
  const path = allPaths(state.queryResult)[state.selectedPath]
  return (path?.edges || []).flatMap((edge) => (edge.evidence || []).map((record) => ({ edge, record })))
}

function selectedRelationshipEvidence() {
  const relationship = state.payload.relationships[state.selectedRelationship]
  if (!relationship) return null
  return {
    relationship,
    chunk: state.payload.chunks.find((chunk) => chunk.chunk_id === relationship.source_id),
  }
}

let state = {
  screen: 'home',
  payload: emptyPayload(),
  documents: [],
  approvals: new Set(),
  queryResult: null,
  messages: loadConversation(),
  selectedRelationship: 0,
  selectedPath: 0,
  backend: {
    connected: false,
    extractor: { provider: 'anthropic', configured: false, model: null },
    facilities: [],
  },
  providerForm: { provider: 'anthropic', model: 'claude-sonnet-5', key: '' },
  busy: null,
  notice: 'Connect PRECISO MCP, configure an LLM provider, then add source documents.',
  error: '',
  snapshotDate: new Date().toISOString().slice(0, 10),
  detailsOpen: true,
}

function render() {
  app.innerHTML = state.screen === 'home' ? renderHome() : renderWorkbench()
  bindEvents()
}

function statusLabel() {
  if (!state.backend.connected) return 'MCP offline'
  if (!state.backend.extractor.configured) return 'Provider needed'
  return 'Ready'
}

function extractorLabel() {
  return state.backend.extractor.configured
    ? `${state.backend.extractor.provider || 'provider'} / ${state.backend.extractor.model || 'configured'}`
    : 'No LLM key configured'
}

function renderHome() {
  return `<main class="home-shell">
    <header class="home-nav">
      <button class="home-brand" type="button" data-action="home">THE SUPPLY CENTER</button>
      <nav aria-label="Home sections">
        <a href="#overview"><span>01</span>Overview</a>
        <a href="#workflow"><span>02</span>Workflow</a>
        <a href="#evidence"><span>03</span>Evidence</a>
      </nav>
      <button class="home-start" type="button" data-action="workspace">Get Started</button>
    </header>

    <section class="home-hero" id="overview">
      <div class="hero-copy">
        <p class="home-kicker">Supply-chain analyst interface</p>
        <h1>Trace what depends on what.</h1>
        <p>Configure your LLM provider, send source documents through the local analyst agent, and let PRECISO MCP validate the graph before any answer is treated as evidence.</p>
        <div class="home-actions">
          <button class="home-primary" type="button" data-action="workspace">Get Started</button>
          <a href="#workflow">See Workflow</a>
        </div>
      </div>
      <div class="dependency-board" aria-label="Supply-chain dependency diagram">
        <div class="board-top">
          <span>PRECISO MCP / SUPPLY CHAIN</span>
          <strong>EMPTY WORKSPACE</strong>
        </div>
        <div class="board-grid"></div>
        <div class="board-node facility"><span>FACILITY</span><b>source claim</b></div>
        <div class="board-node component"><span>COMPONENT</span><b>reviewed edge</b></div>
        <div class="board-node product one"><span>PRODUCT</span><b>exposure path</b></div>
        <div class="board-node product two"><span>EVIDENCE</span><b>source chunk</b></div>
        <div class="board-route route-a"></div>
        <div class="board-route route-b"></div>
        <div class="board-route route-c"></div>
        <p>Analyst-supplied documents only</p>
      </div>
    </section>

    <section class="home-strip">
      <span>LLM CONFIGURATION</span>
      <i></i>
      <span>DOCUMENT EXTRACTION</span>
      <i></i>
      <span>HUMAN REVIEW</span>
      <i></i>
      <span>PRECISO MCP QUERY</span>
    </section>

    <section class="home-section workflow-section" id="workflow">
      <div>
        <p class="home-kicker">Workflow</p>
        <h2>One console, three gates.</h2>
      </div>
      <div class="workflow-grid">
        <article>
          <span>01</span>
          <h3>Configure</h3>
          <p>Set the provider key for this local API process and check whether PRECISO MCP is reachable.</p>
        </article>
        <article>
          <span>02</span>
          <h3>Review</h3>
          <p>Upload source documents, extract direct supply-chain claims, and approve only supported relationships.</p>
        </article>
        <article>
          <span>03</span>
          <h3>Trace</h3>
          <p>Ask facility-unavailable questions and inspect the exact path evidence behind each answer.</p>
        </article>
      </div>
    </section>

    <section class="home-section evidence-section" id="evidence">
      <div>
        <p class="home-kicker">Evidence</p>
        <h2>Answers stay attached to source text.</h2>
      </div>
      <div class="evidence-slab">
        <span>DIRECTED EDGE</span>
        <p>Facility -> component -> product is accepted only after the relationship cites a source chunk and passes PRECISO validation.</p>
      </div>
    </section>
  </main>`
}

function renderWorkbench() {
  const relationships = state.payload.relationships || []
  const paths = allPaths(state.queryResult)
  const accepted = state.approvals.size
  const pathEvidence = selectedPathEvidence()
  const relationshipEvidence = selectedRelationshipEvidence()

  return `<main class="analyst-workbench ${state.detailsOpen ? '' : 'details-closed'}">
    <header class="topbar">
      <div class="status-cluster">
        <span class="status-dot ${state.backend.connected ? 'online' : ''}"></span>
        <span>${escapeHTML(statusLabel())}</span>
      </div>
      <div class="center-title">
        <span>Supply-chain analyst</span>
        <strong>Evidence-backed dependency tracing</strong>
      </div>
      <button class="wordmark" type="button" aria-label="The Supply Center">THE SUPPLY CENTER</button>
    </header>

    <section class="setup-panel" aria-label="Setup">
      <div class="panel-heading">
        <span>01</span>
        <h2>Setup</h2>
      </div>
      <form class="provider-card" id="provider-form">
        <label>
          <span>Provider</span>
          <select name="provider">
            <option value="anthropic" ${state.providerForm.provider === 'anthropic' ? 'selected' : ''}>Anthropic</option>
          </select>
        </label>
        <label>
          <span>Model</span>
          <input name="model" value="${escapeHTML(state.providerForm.model)}" autocomplete="off" />
        </label>
        <label class="key-field">
          <span>LLM API key</span>
          <input name="key" type="password" value="${escapeHTML(state.providerForm.key)}" placeholder="Stored in this local API process only" autocomplete="off" />
        </label>
        <button class="solid-button" type="submit" ${state.busy ? 'disabled' : ''}>Configure agent</button>
        <p>${escapeHTML(extractorLabel())}</p>
      </form>

      <div class="mcp-card">
        <div>
          <span class="label">PRECISO MCP</span>
          <strong>${state.backend.connected ? 'Connected' : 'Not connected'}</strong>
        </div>
        <button type="button" data-action="refresh-status">Refresh</button>
      </div>

      <section class="sources-block">
        <div class="section-line">
          <span>Sources</span>
          <b>${state.documents.length}</b>
        </div>
        <input id="source-upload" type="file" multiple accept=".md,.txt,.csv,.json" hidden />
        <button class="upload-zone" type="button" data-action="upload">
          <strong>Add source documents</strong>
          <span>Markdown, text, CSV, or JSON</span>
        </button>
        <div class="source-list">
          ${state.documents.length ? state.documents.map((document) => `<div class="source-row">
            <b>${escapeHTML(document.name)}</b>
            <small>${escapeHTML(document.meta || 'ready')}</small>
          </div>`).join('') : '<p>No documents loaded. Add your source files to begin.</p>'}
        </div>
        <label class="date-row">
          <span>Effective date</span>
          <input type="date" data-snapshot value="${escapeHTML(state.snapshotDate)}" />
        </label>
        <button class="solid-button" type="button" data-action="extract" ${!state.documents.length || !state.backend.extractor.configured || state.busy ? 'disabled' : ''}>
          ${state.busy === 'extract' ? 'Extracting relationships' : 'Extract relationships'}
        </button>
      </section>
    </section>

    <section class="conversation-panel" aria-label="Analyst chat">
      <div class="conversation-scroll">
        <div class="conversation-kicker">Documented paths only</div>
        <h1>Ask what depends on a facility.</h1>
        <p class="lede">The analyst agent converts reviewed source claims into facility-to-product paths through PRECISO MCP. Every answer should stay source-backed and inspectable.</p>
        <div class="notice-strip ${state.error ? 'error' : ''}">${escapeHTML(state.error || state.notice)}</div>
        <div class="conversation-history">
          ${state.messages.length ? state.messages.map(renderMessage).join('') : renderEmptyThread()}
          ${state.busy === 'chat' ? renderLoadingTurn() : ''}
        </div>
      </div>
      <form class="composer" id="composer">
        <textarea name="message" rows="1" placeholder="Example: Which products are exposed if facility:&lt;company&gt;:&lt;site&gt; is unavailable?"></textarea>
        <button type="submit" ${state.busy ? 'disabled' : ''}>Send</button>
        <small>Routes supported facility-unavailable questions to PRECISO MCP.</small>
      </form>
    </section>

    ${state.detailsOpen ? renderDetails(relationships, paths, accepted, pathEvidence, relationshipEvidence) : ''}
  </main>`
}

function renderEmptyThread() {
  return `<article class="empty-thread">
    <span>Analyst workspace ready</span>
    <p>Configure the provider, upload sources, review relationships, ingest facts, then ask an exposure question.</p>
  </article>`
}

function renderLoadingTurn() {
  return `<article class="message assistant-turn"><div class="message-meta">THE SUPPLY CENTER</div><p>Tracing documented dependencies through PRECISO MCP...</p></article>`
}

function renderMessage(message) {
  if (message.role === 'user') {
    return `<article class="message user-turn"><div class="message-meta">You</div><p>${escapeHTML(message.text)}</p></article>`
  }
  const paths = allPaths(message.result)
  return `<article class="message assistant-turn">
    <div class="message-meta">THE SUPPLY CENTER <span>${escapeHTML(message.mode || 'agent')}</span></div>
    <p>${escapeHTML(message.text)}</p>
    ${message.result ? renderInlineResult(message.result, paths) : ''}
  </article>`
}

function renderInlineResult(result, paths) {
  if (result.status !== 'success') {
    return `<div class="inline-status">${escapeHTML(result.message || result.status)}</div>`
  }
  return `<div class="inline-result">
    <div><strong>${result.potentially_exposed_products.length}</strong><span>products</span></div>
    <div><strong>${paths.length}</strong><span>paths</span></div>
    <p>${result.completeness?.is_truncated ? 'Result reached the path limit.' : 'Complete within the documented graph and requested path limit.'}</p>
    <div class="product-strip">${result.potentially_exposed_products.map((product) => `<span>${escapeHTML(displayName(product.product_id))}</span>`).join('')}</div>
  </div>`
}

function renderDetails(relationships, paths, accepted, pathEvidence, relationshipEvidence) {
  return `<aside class="details-panel" aria-label="Evidence">
    <div class="panel-heading">
      <span>02</span>
      <h2>Review</h2>
    </div>
    <section class="review-block">
      <div class="section-line">
        <span>Extracted relationships</span>
        <b>${accepted}/${relationships.length}</b>
      </div>
      <div class="relationship-list">
        ${relationships.length ? relationships.map((edge, index) => `<label class="relationship-row ${state.selectedRelationship === index ? 'selected' : ''}">
          <input type="checkbox" data-approval="${index}" ${state.approvals.has(index) ? 'checked' : ''} />
          <button type="button" data-relationship="${index}">
            <span>${escapeHTML(relationshipType(edge))}</span>
            <b>${escapeHTML(displayName(edge.src_id))} -> ${escapeHTML(displayName(edge.tgt_id))}</b>
            <small>${escapeHTML(edge.source_id || 'source pending')}</small>
          </button>
        </label>`).join('') : '<p>No extracted relationships yet.</p>'}
      </div>
      <button class="solid-button" type="button" data-action="ingest" ${!accepted || state.busy ? 'disabled' : ''}>
        ${state.busy === 'ingest' ? 'Validating in PRECISO' : `Ingest ${accepted} approved`}
      </button>
    </section>

    <section class="review-block">
      <div class="section-line">
        <span>Dependency paths</span>
        <b>${paths.length}</b>
      </div>
      <div class="path-list">
        ${paths.length ? paths.map((path, index) => `<button type="button" data-path="${index}" class="${state.selectedPath === index ? 'selected' : ''}">
          <small>PATH ${String(index + 1).padStart(2, '0')}</small>
          <span>${path.nodes.map((node) => escapeHTML(displayName(node))).join(' -> ')}</span>
        </button>`).join('') : `<p>${escapeHTML(state.queryResult?.message || 'Run an investigation after ingestion.')}</p>`}
      </div>
    </section>

    <section class="review-block evidence-block">
      <div class="section-line">
        <span>Evidence</span>
        <b>${pathEvidence.length || (relationshipEvidence?.chunk ? 1 : 0)}</b>
      </div>
      ${renderEvidence(pathEvidence, relationshipEvidence)}
    </section>
  </aside>`
}

function renderEvidence(pathEvidence, relationshipEvidence) {
  if (pathEvidence.length) {
    return pathEvidence.map(({ edge, record }) => `<article class="evidence-record">
      <small>${escapeHTML(fileName(record.file_path))} / ${escapeHTML(record.chunk?.chunk_id || record.source_id)}</small>
      <blockquote>${escapeHTML(record.chunk?.content || 'Evidence text unavailable.')}</blockquote>
      <p>${escapeHTML(relationshipType(edge))}: ${escapeHTML(displayName(edge.src_id))} -> ${escapeHTML(displayName(edge.tgt_id))}</p>
    </article>`).join('')
  }
  if (relationshipEvidence?.chunk) {
    return `<article class="evidence-record">
      <small>${escapeHTML(fileName(relationshipEvidence.relationship.file_path))} / ${escapeHTML(relationshipEvidence.chunk.chunk_id)}</small>
      <blockquote>${escapeHTML(relationshipEvidence.chunk.content)}</blockquote>
      <p>${escapeHTML(displayName(relationshipEvidence.relationship.src_id))} -> ${escapeHTML(displayName(relationshipEvidence.relationship.tgt_id))}</p>
    </article>`
  }
  return '<p>Select a relationship or run an investigation to inspect source evidence.</p>'
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string'
      ? body.detail
      : body.detail?.configured === false
        ? 'LLM extraction is not configured on the API process.'
        : `Request failed (${response.status}).`
    throw new Error(detail)
  }
  return body
}

async function checkBackend() {
  try {
    const [status, capabilities] = await Promise.all([api('/api/status'), api('/api/capabilities')])
    state.backend = {
      connected: status.engine?.status !== 'error',
      extractor: status.extractor || { provider: 'anthropic', configured: false, model: null },
      facilities: capabilities.facilities || [],
    }
    state.notice = state.backend.connected
      ? 'PRECISO MCP is reachable. Add documents to create a reviewed graph.'
      : 'PRECISO MCP is not reachable. Check the local API process environment.'
  } catch (error) {
    state.backend = { ...state.backend, connected: false }
    state.notice = `Local API unavailable: ${error.message}`
  }
  render()
}

async function configureProvider(event) {
  event.preventDefault()
  const form = event.currentTarget
  const body = {
    provider: form.elements.provider.value,
    model: form.elements.model.value.trim(),
    api_key: form.elements.key.value.trim(),
  }
  state.providerForm = { provider: body.provider, model: body.model, key: body.api_key }
  state.busy = 'provider'
  state.error = ''
  state.notice = 'Configuring the local analyst agent...'
  render()
  try {
    const result = await api('/api/provider', { method: 'POST', body: JSON.stringify(body) })
    state.backend.extractor = result.extractor
    state.providerForm.key = ''
    state.notice = 'Provider configured for this local API process.'
  } catch (error) {
    state.error = error.message
  } finally {
    state.providerForm.key = ''
    state.busy = null
    render()
  }
}

async function extractDocuments() {
  state.busy = 'extract'
  state.error = ''
  state.notice = 'The LLM is extracting direct documented relationships...'
  render()
  try {
    const result = await api('/api/extract', {
      method: 'POST',
      body: JSON.stringify({
        snapshot_effective_date: state.snapshotDate,
        documents: state.documents.map(({ name, content }) => ({ name, content })),
      }),
    })
    localStorage.setItem(RAW_EXTRACTION_KEY, result.raw_output || '')
    state.payload = result.payload || emptyPayload()
    state.approvals = new Set((state.payload.relationships || []).map((_, index) => index))
    state.selectedRelationship = 0
    state.queryResult = null
    state.notice = `${result.model || 'Provider'} proposed ${state.payload.relationships?.length || 0} relationships. Review before ingestion.`
  } catch (error) {
    state.error = error.message
  } finally {
    state.busy = null
    render()
  }
}

async function ingestApproved() {
  const relationships = state.payload.relationships.filter((_, index) => state.approvals.has(index))
  const entityIds = new Set(relationships.flatMap((edge) => [edge.src_id, edge.tgt_id]))
  const sourceIds = new Set(relationships.map((edge) => edge.source_id))
  const payload = {
    ...state.payload,
    relationships,
    entities: state.payload.entities.filter((entity) => entityIds.has(entity.entity_name)),
    chunks: state.payload.chunks.filter((chunk) => sourceIds.has(chunk.chunk_id)),
  }
  state.busy = 'ingest'
  state.error = ''
  state.notice = 'PRECISO MCP is validating approved relationships...'
  render()
  try {
    const result = await api('/api/ingest', { method: 'POST', body: JSON.stringify({ approved: true, payload }) })
    if (result.status !== 'success') throw new Error(result.message || 'PRECISO rejected the extraction payload.')
    state.notice = `Accepted by PRECISO. ${relationships.length} relationships are ready for investigation.`
  } catch (error) {
    state.error = error.message
  } finally {
    state.busy = null
    render()
  }
}

async function ask(message) {
  const question = message.trim()
  if (!question || state.busy) return
  state.messages.push({ role: 'user', text: question })
  state.busy = 'chat'
  state.error = ''
  persistConversation()
  render()
  try {
    const response = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message: question, max_paths: 100 }) })
    const result = response.result || response
    if (response.result) {
      state.queryResult = response.result
      state.selectedPath = 0
    }
    const text = result.status === 'success'
      ? `${response.facility_name || displayName(result.scenario?.facility_id)} has ${allPaths(result).length} documented path${allPaths(result).length === 1 ? '' : 's'} to ${result.potentially_exposed_products.length} potentially exposed product${result.potentially_exposed_products.length === 1 ? '' : 's'}. This is dependency evidence, not delay or severity prediction.`
      : result.message || response.message || 'The investigation could not be completed.'
    state.messages.push({ role: 'assistant', text, result: response.result || null, mode: 'PRECISO MCP' })
  } catch (error) {
    state.messages.push({ role: 'assistant', text: `The local backend is unavailable: ${error.message}`, mode: 'Connection error' })
  } finally {
    state.busy = null
    persistConversation()
    render()
    requestAnimationFrame(() => document.querySelector('.conversation-scroll')?.scrollTo({ top: 999999, behavior: 'smooth' }))
  }
}

function bindEvents() {
  document.querySelectorAll('[data-action="home"]').forEach((button) => {
    button.addEventListener('click', () => {
      state.screen = 'home'
      render()
      window.scrollTo(0, 0)
    })
  })
  document.querySelectorAll('[data-action="workspace"]').forEach((button) => {
    button.addEventListener('click', () => {
      state.screen = 'workspace'
      render()
      checkBackend()
    })
  })
  document.querySelector('#provider-form')?.addEventListener('submit', configureProvider)
  document.querySelector('[data-action="refresh-status"]')?.addEventListener('click', checkBackend)
  document.querySelectorAll('[data-action="upload"]').forEach((button) => {
    button.addEventListener('click', () => document.querySelector('#source-upload')?.click())
  })
  document.querySelector('[data-action="extract"]')?.addEventListener('click', extractDocuments)
  document.querySelector('[data-action="ingest"]')?.addEventListener('click', ingestApproved)
  document.querySelector('[data-snapshot]')?.addEventListener('change', (event) => { state.snapshotDate = event.target.value })
  document.querySelectorAll('[data-relationship]').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedRelationship = Number(button.dataset.relationship)
      render()
    })
  })
  document.querySelectorAll('[data-path]').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedPath = Number(button.dataset.path)
      render()
    })
  })
  document.querySelectorAll('[data-approval]').forEach((checkbox) => {
    checkbox.addEventListener('change', (event) => {
      const index = Number(event.target.dataset.approval)
      event.target.checked ? state.approvals.add(index) : state.approvals.delete(index)
      render()
    })
  })
  document.querySelector('#source-upload')?.addEventListener('change', async (event) => {
    const files = Array.from(event.target.files || [])
    const allowed = new Set(['md', 'txt', 'csv', 'json'])
    const invalid = files.filter((file) => !allowed.has(file.name.split('.').at(-1)?.toLowerCase()))
    if (invalid.length) {
      state.error = `Unsupported files: ${invalid.map((file) => file.name).join(', ')}. Use MD, TXT, CSV, or JSON.`
      render()
      return
    }
    state.documents = await Promise.all(files.map(async (file) => ({
      name: file.name,
      content: await file.text(),
      meta: `${Math.max(1, Math.ceil(file.size / 1024))} KB ready`,
    })))
    state.payload = emptyPayload()
    state.approvals = new Set()
    state.queryResult = null
    state.notice = `${state.documents.length} document${state.documents.length === 1 ? '' : 's'} ready for extraction.`
    state.error = ''
    render()
  })
  const composer = document.querySelector('#composer')
  if (composer) {
    composer.addEventListener('submit', (event) => {
      event.preventDefault()
      const input = composer.elements.message
      const value = input.value
      input.value = ''
      ask(value)
    })
    composer.elements.message.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        composer.requestSubmit()
      }
    })
  }
}

render()
