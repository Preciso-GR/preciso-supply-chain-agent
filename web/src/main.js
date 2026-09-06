import './style.css'
import productMark from './assets/supply-center-mark.svg'
import curatedPayload from '../../fixtures/supply_chain/expected_extraction.json'

const app = document.querySelector('#app')
const NORTHBRIDGE_ID = 'facility:arkon-components:northbridge'
const STORAGE_KEY = 'supply-center-conversation-v1'
const RAW_EXTRACTION_KEY = 'supply-center-last-raw-extraction-v1'

const escapeHTML = (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;')
const relationshipType = (edge) => String(edge.keywords || '').split(',')[0].trim().toUpperCase()
const fileName = (path) => String(path || 'source').split('/').at(-1)

function loadConversation() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(saved) ? saved.slice(-20) : []
  } catch { return [] }
}

function displayName(id) {
  const known = {
    'company:arkon-components': 'Arkon Components', 'company:redwood-materials': 'Redwood Materials',
    'facility:arkon-components:northbridge': 'Northbridge Fabrication Facility', 'facility:arkon-components:lakeside': 'Lakeside Power Module Facility',
    'facility:redwood-materials:harbor': 'Harbor Casting Works', 'component:arkon-components:control-unit-c17': 'Control Unit C-17',
    'component:arkon-components:power-module-p9': 'Power Module P-9', 'component:redwood-materials:valve-body-v2': 'Valve Body V-2',
    'product:aquapump:300': 'AquaPump 300', 'product:aquapump:500': 'AquaPump 500', 'product:valvepro:10': 'ValvePro 10',
  }
  return known[id] || String(id || '').split(':').at(-1)?.replaceAll('-', ' ') || 'Unknown'
}

function buildCuratedQuery(payload, facilityId = NORTHBRIDGE_ID) {
  const chunks = new Map(payload.chunks.map((chunk) => [chunk.chunk_id, chunk]))
  const products = new Map()
  payload.relationships.filter((edge) => edge.src_id === facilityId && relationshipType(edge) === 'MANUFACTURES').forEach((first) => {
    payload.relationships.filter((edge) => edge.src_id === first.tgt_id && relationshipType(edge) === 'USED_IN').forEach((second) => {
      const renderEdge = (edge) => ({ src_id: edge.src_id, relationship_type: relationshipType(edge), tgt_id: edge.tgt_id, evidence: [{ source_id: edge.source_id, file_path: edge.file_path, description: edge.description, chunk: { chunk_id: edge.source_id, content: chunks.get(edge.source_id)?.content || '' } }] })
      const path = { nodes: [facilityId, first.tgt_id, second.tgt_id], edges: [renderEdge(first), renderEdge(second)] }
      products.set(second.tgt_id, [...(products.get(second.tgt_id) || []), path])
    })
  })
  return { status: products.size ? 'success' : 'no_documented_paths', workspace: 'supply_chain', snapshot: { effective_dates: [payload.snapshot_effective_date], document_ids: [payload.document_id] }, scenario: { type: 'facility_unavailable', facility_id: facilityId, hypothetical: true }, message: products.size ? 'Documented dependency paths found.' : 'No documented paths found in the curated sample.', potentially_exposed_products: [...products.entries()].sort().map(([product_id, paths]) => ({ product_id, conclusion: 'Potentially exposed through documented dependencies.', paths })), completeness: { is_truncated: false, max_paths: 100 }, limitations: ['Potential exposure through documented dependencies only.', 'Does not establish delay, severity, inventory shortage, capacity, or business impact.'] }
}

function allPaths(result) { return (result?.potentially_exposed_products || []).flatMap((product) => product.paths || []) }

function documentsFromPayload(payload) {
  const documents = new Map()
  payload.chunks.forEach((chunk) => {
    const name = fileName(chunk.file_path)
    const existing = documents.get(name)
    documents.set(name, {
      name,
      content: `${existing?.content || ''}${existing ? '\n\n' : ''}${chunk.content}`,
      meta: `source evidence · ${payload.snapshot_effective_date}`,
      ext: name.split('.').at(-1).toUpperCase(),
    })
  })
  return [...documents.values()]
}

let state = {
  screen: 'home', payload: structuredClone(curatedPayload), dataMode: 'curated_sample', documents: [],
  approvals: new Set(curatedPayload.relationships.map((_, index) => index)), queryResult: buildCuratedQuery(curatedPayload),
  messages: loadConversation(), selectedRelationship: 3, selectedPath: 0,
  backend: { connected: false, extractor: { configured: false, model: null } }, busy: null,
  notice: 'Curated sample loaded — extraction accuracy is not implied.', error: '', snapshotDate: curatedPayload.snapshot_effective_date, railOpen: true,
}
state.documents = documentsFromPayload(curatedPayload)

function persistConversation() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.messages.slice(-20))) }
function render() { app.innerHTML = state.screen === 'home' ? renderHome() : renderWorkspace(); bindEvents() }

function renderHome() {
  return `<main class="site-shell home-shell"><header class="site-nav"><button class="brand" data-action="home"><img class="brand-logo" src="${productMark}" alt=""/><span class="brand-copy"><strong>SUPPLY CENTER</strong><small>powered by PRECISO</small></span></button><nav class="nav-links"><a href="#product"><span>01</span>Overview</a><a href="#workflow"><span>02</span>Workflow</a><a href="#evidence"><span>03</span>Evidence</a></nav><button class="small-cta" data-action="workspace">Open center</button></header>
  <section class="hero" id="product"><div class="hero-copy"><p class="eyebrow">Evidence-aware dependency intelligence</p><h1>Know what<br/><em>breaks next.</em></h1><p class="hero-lede">Turn source documents into reviewable facility-to-product paths. Every conclusion stays connected to the statements that support it.</p><div class="hero-actions"><button class="primary-cta" data-action="workspace">Get started</button><a class="secondary-cta" href="#workflow">See the workflow</a></div><div class="hero-proof"><span>01</span><b>Source-backed</b><span>02</span><b>Human-reviewed</b><span>03</span><b>Path-complete</b></div></div><div class="hero-visual"><div class="map-header"><span>IMPACT TRACE / SAMPLE</span><strong>2 PRODUCTS EXPOSED</strong></div><div class="map-grid"></div><div class="map-node facility-node"><span>FACILITY</span><b>Northbridge</b><small>Scenario input</small></div><div class="map-node component-node"><span>COMPONENT</span><b>Control Unit C-17</b><small>Documented edge</small></div><div class="map-node product-node product-one"><span>PRODUCT</span><b>AquaPump 300</b></div><div class="map-node product-node product-two"><span>PRODUCT</span><b>AquaPump 500</b></div><div class="orbit-caption">Synthetic snapshot · 2026-01-15</div></div></section>
  <section class="ticker"><span>DOCUMENTS</span><i></i><span>EXTRACTION</span><i></i><span>HUMAN REVIEW</span><i></i><span>DETERMINISTIC PATHS</span><i></i><span>EDGE EVIDENCE</span></section>
  <section class="feature-section" id="workflow"><div class="section-heading"><p class="eyebrow">One deliberate workflow</p><h2>Documents in.<br/><span>Defensible paths out.</span></h2><p>Claude proposes graph facts. You review them. PRECISO validates, stores, and traverses accepted relationships.</p></div><div class="feature-grid"><article class="feature-card"><div class="feature-number">01</div><h3>Add text sources</h3><p>Bring facility registers, BOM summaries, CSV exports, or Markdown notes.</p></article><article class="feature-card"><div class="feature-number">02</div><h3>Review extraction</h3><p>Accept only direct claims with canonical IDs and resolvable evidence.</p></article><article class="feature-card"><div class="feature-number">03</div><h3>Investigate</h3><p>Ask which products have documented exposure to a facility scenario.</p></article></div></section>
  <section class="evidence-section" id="evidence"><div class="evidence-copy"><p class="eyebrow">No black boxes</p><h2>Every edge<br/><span>has a receipt.</span></h2><p>The answer shows the exact source chunk behind each directed relationship.</p><button class="secondary-cta" data-action="workspace">Open the sample center</button></div><div class="evidence-card"><div class="evidence-card-top"><span>DIRECT EVIDENCE</span><span>facility_001</span></div><blockquote>“Northbridge Fabrication Facility manufactures Control Unit C-17.”</blockquote><div class="evidence-meta"><span>facility_register.md</span><span>2026-01-15</span></div></div></section><footer class="site-footer"><div class="brand-copy"><strong>SUPPLY CENTER</strong><small>powered by PRECISO</small></div><p>Potential exposure through documented dependencies only.</p></footer></main>`
}

function currentRelationship() { return state.payload?.relationships?.[state.selectedRelationship] || state.payload?.relationships?.[0] }
function selectedEvidence() { const relationship = currentRelationship(); if (!relationship) return null; return { relationship, chunk: state.payload.chunks.find((item) => item.chunk_id === relationship.source_id) } }
function selectedPathEvidence() {
  const path = allPaths(state.queryResult)[state.selectedPath]
  return (path?.edges || []).flatMap((edge) => (edge.evidence || []).map((record) => ({ edge, record })))
}

function renderMessage(message) {
  if (message.role === 'user') return `<article class="message user-turn"><div class="message-role">You</div><p>${escapeHTML(message.text)}</p></article>`
  const paths = allPaths(message.result)
  return `<article class="message assistant-turn"><div class="assistant-heading"><img src="${productMark}" alt=""/><span>SUPPLY CENTER</span><small>${escapeHTML(message.mode || 'system')}</small></div><p>${escapeHTML(message.text)}</p>${message.result ? renderInlineResult(message.result, paths) : ''}</article>`
}

function renderInlineResult(result, paths) {
  if (result.status !== 'success') return `<div class="inline-status warning">${escapeHTML(result.message || result.status)}</div>`
  return `<div class="inline-result"><div class="result-summary"><strong>${result.potentially_exposed_products.length}</strong><span>products</span><strong>${paths.length}</strong><span>paths</span></div><div class="inline-products">${result.potentially_exposed_products.map((product) => `<span>${escapeHTML(displayName(product.product_id))}</span>`).join('')}</div><p>${result.completeness?.is_truncated ? 'Result truncated by the path limit.' : 'Complete within the documented graph and requested path limit.'}</p></div>`
}

function renderWorkspace() {
  const relationships = state.payload?.relationships || []; const paths = allPaths(state.queryResult); const evidence = selectedEvidence(); const pathEvidence = selectedPathEvidence(); const accepted = state.approvals.size
  const engineLabel = state.backend.connected ? 'PRECISO connected' : 'Preview only'; const extractorLabel = state.backend.extractor.configured ? state.backend.extractor.model : 'Claude key needed'
  return `<main class="workbench ${state.railOpen ? '' : 'rail-closed'}"><header class="workbench-bar"><button class="compact-brand" data-action="home"><img src="${productMark}" alt=""/><span>SUPPLY CENTER</span></button><div class="workbench-title"><small>Center</small><strong>Northbridge supply-chain review</strong></div><div class="workbench-actions"><span class="connection-dot ${state.backend.connected ? 'online' : ''}"></span><span>${engineLabel}</span><button data-action="toggle-rail">${state.railOpen ? 'Hide details' : 'Show details'}</button></div></header>
  <section class="conversation-pane"><div class="conversation-scroll"><div class="conversation-header"><p class="eyebrow">Supply-chain analyst</p><h1>What do you need to trace?</h1><p>Ask about documented exposure from a facility. SUPPLY CENTER returns paths and evidence—not forecasts.</p><div class="suggested-prompts"><button data-prompt="What products are exposed if Northbridge Fabrication Facility becomes unavailable?">Investigate Northbridge</button><button data-prompt="What products are exposed if Harbor Casting Works becomes unavailable?">Investigate Harbor</button><button data-prompt="What products are exposed if Plant 7 becomes unavailable?">Test ambiguous identity</button></div></div><div class="conversation-history">${state.messages.length ? state.messages.map(renderMessage).join('') : `<article class="empty-thread"><span>Ready</span><p>Add documents or use the curated sample, then ask a facility-unavailable question.</p></article>`}${state.busy === 'chat' ? `<article class="message assistant-turn loading-turn"><div class="assistant-heading"><img src="${productMark}" alt=""/><span>SUPPLY CENTER</span></div><p>Tracing documented dependencies…</p></article>` : ''}</div></div>
  <form class="composer" id="composer"><input id="source-upload" type="file" multiple accept=".md,.txt,.csv,.json" hidden/><button type="button" class="attach-button" data-action="upload">Add files</button><textarea name="message" rows="1" placeholder="Ask which products are exposed if a facility is unavailable…"></textarea><button class="send-button" type="submit" ${state.busy ? 'disabled' : ''}>Send</button><small>Documented dependencies only · no delay or severity prediction</small></form></section>
  ${state.railOpen ? renderRail(relationships, paths, evidence, pathEvidence, accepted, extractorLabel) : ''}</main>`
}

function renderRail(relationships, paths, evidence, pathEvidence, accepted, extractorLabel) {
  return `<aside class="environment-rail"><div class="rail-heading"><div><small>Environment</small><h2>Analysis context</h2></div><button data-action="clear-conversation">Clear chat</button></div>${state.notice ? `<div class="rail-notice">${escapeHTML(state.notice)}</div>` : ''}${state.error ? `<div class="rail-error">${escapeHTML(state.error)}</div>` : ''}
  <section class="rail-section"><div class="rail-section-title"><span>Sources</span><b>${state.documents.length}</b></div><div class="source-list">${state.documents.length ? state.documents.map((document) => `<div><span class="file-type">${escapeHTML(document.ext || 'TXT')}</span><span><b>${escapeHTML(document.name)}</b><small>${escapeHTML(document.meta || 'ready')}</small></span></div>`).join('') : '<p>No documents added.</p>'}</div><div class="source-actions"><button data-action="upload">Add documents</button><label>Effective date<input type="date" data-snapshot value="${escapeHTML(state.snapshotDate)}"/></label><button class="primary-action" data-action="extract" ${!state.documents.length || !state.backend.extractor.configured || state.busy ? 'disabled' : ''}>${state.busy === 'extract' ? 'Extracting…' : 'Extract with Claude'}</button><button data-action="sample">Use curated sample</button></div><p class="provider-note">Extractor: ${escapeHTML(extractorLabel)}. Keys stay in the local API process.</p></section>
  <section class="rail-section" id="approval"><div class="rail-section-title"><span>Relationship review</span><b>${accepted}/${relationships.length}</b></div><div class="relationship-list">${relationships.length ? relationships.map((edge, index) => `<label class="relationship-row ${state.selectedRelationship === index ? 'selected' : ''}"><input type="checkbox" data-approval="${index}" ${state.approvals.has(index) ? 'checked' : ''}/><button type="button" data-relationship="${index}"><span>${escapeHTML(relationshipType(edge))}</span><b>${escapeHTML(displayName(edge.src_id))} → ${escapeHTML(displayName(edge.tgt_id))}</b><small>${escapeHTML(edge.source_id)}</small></button></label>`).join('') : '<p>Extract documents to create proposals.</p>'}</div><button class="rail-primary" data-action="ingest" ${!accepted || state.busy ? 'disabled' : ''}>${state.busy === 'ingest' ? 'Validating and ingesting…' : `Ingest ${accepted} approved relationships`}</button></section>
  <section class="rail-section"><div class="rail-section-title"><span>Dependency paths</span><b>${paths.length}</b></div><div class="rail-paths">${paths.length ? paths.map((path, index) => `<button data-path="${index}" class="${state.selectedPath === index ? 'selected' : ''}"><small>PATH ${String(index + 1).padStart(2, '0')}</small><span>${path.nodes.map((node) => escapeHTML(displayName(node))).join(' → ')}</span></button>`).join('') : `<p>${escapeHTML(state.queryResult?.message || 'Run an investigation to see paths.')}</p>`}</div>${state.queryResult ? `<div class="completeness ${state.queryResult.completeness?.is_truncated ? 'warning' : ''}">${state.queryResult.completeness?.is_truncated ? 'Truncated result' : 'Complete for documented graph'}<small>Snapshot: ${escapeHTML(state.queryResult.snapshot?.effective_dates?.join(', ') || 'unknown')}</small></div>` : ''}</section>
  <section class="rail-section"><div class="rail-section-title"><span>${pathEvidence.length ? 'Selected path evidence' : 'Relationship evidence'}</span><b>${pathEvidence.length || (evidence?.chunk ? 1 : 0)}</b></div>${pathEvidence.length ? pathEvidence.map(({ edge, record }) => `<div class="evidence-record"><small>${escapeHTML(fileName(record.file_path))} / ${escapeHTML(record.chunk?.chunk_id || record.source_id)}</small><blockquote>${escapeHTML(record.chunk?.content || 'Evidence text unavailable.')}</blockquote><p><b>${escapeHTML(relationshipType(edge))}</b> · ${escapeHTML(displayName(edge.src_id))} → ${escapeHTML(displayName(edge.tgt_id))}</p></div>`).join('') : evidence?.chunk ? `<div class="evidence-record"><small>${escapeHTML(fileName(evidence.relationship.file_path))} / ${escapeHTML(evidence.chunk.chunk_id)}</small><blockquote>${escapeHTML(evidence.chunk.content)}</blockquote><p>Supports <b>${escapeHTML(displayName(evidence.relationship.src_id))} → ${escapeHTML(displayName(evidence.relationship.tgt_id))}</b></p></div>` : '<p>Select a relationship or run an investigation to inspect its source.</p>'}</section></aside>`
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) } }); const body = await response.json().catch(() => ({}))
  if (!response.ok) { const detail = typeof body.detail === 'string' ? body.detail : body.detail?.configured === false ? 'Claude extraction is not configured on the API process.' : `Request failed (${response.status}).`; throw new Error(detail) }
  return body
}

async function checkBackend() {
  try { const status = await api('/api/status'); state.backend = { connected: status.engine?.status !== 'error', extractor: status.extractor || { configured: false } } } catch { state.backend = { connected: false, extractor: { configured: false, model: null } } }
  if (state.screen === 'workspace') render()
}

async function extractDocuments() {
  state.busy = 'extract'; state.error = ''; state.notice = 'Claude is extracting direct documented relationships…'; render()
  try { const result = await api('/api/extract', { method: 'POST', body: JSON.stringify({ snapshot_effective_date: state.snapshotDate, documents: state.documents.map(({ name, content }) => ({ name, content })) }) }); localStorage.setItem(RAW_EXTRACTION_KEY, result.raw_output || ''); state.payload = result.payload; state.dataMode = 'claude_extraction'; state.approvals = new Set((result.payload.relationships || []).map((_, index) => index)); state.selectedRelationship = 0; state.queryResult = null; state.notice = `Claude ${result.model} proposed ${result.payload.relationships?.length || 0} relationships. Review before ingestion.` } catch (error) { state.error = error.message; state.notice = 'Extraction did not complete. Uploaded documents remain available.' } finally { state.busy = null; render() }
}

async function ingestApproved() {
  state.busy = 'ingest'; state.error = ''; state.notice = 'PRECISO is validating approved relationships…'; render()
  const relationships = state.payload.relationships.filter((_, index) => state.approvals.has(index)); const entityIds = new Set(relationships.flatMap((edge) => [edge.src_id, edge.tgt_id])); const entities = state.payload.entities.filter((entity) => entityIds.has(entity.entity_name)); const sourceIds = new Set([...relationships.map((edge) => edge.source_id), ...entities.map((entity) => entity.source_id)]); const payload = { ...state.payload, relationships, entities, chunks: state.payload.chunks.filter((chunk) => sourceIds.has(chunk.chunk_id)) }
  try { const result = await api('/api/ingest', { method: 'POST', body: JSON.stringify({ approved: true, payload }) }); if (result.status !== 'success') throw new Error(result.message || 'PRECISO rejected the extraction payload.'); state.dataMode = 'live'; state.notice = `Accepted by PRECISO. ${relationships.length} relationships are ready for investigation.` } catch (error) { state.error = error.message; state.notice = 'Ingestion was rejected. The untouched model output remains saved locally.' } finally { state.busy = null; render() }
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
    if (state.dataMode === 'curated_sample' && question.toLowerCase().includes('northbridge')) {
      const result = buildCuratedQuery(state.payload)
      state.queryResult = result
      state.selectedPath = 0
      state.messages.push({
        role: 'assistant',
        text: 'The curated sample contains two documented Northbridge paths to AquaPump 300 and AquaPump 500. This is fixture data, not a live engine response.',
        result,
        mode: 'Curated sample',
      })
      return
    }
    const response = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message: question, max_paths: 100 }) })
    const result = response.result || response
    if (response.result) { state.queryResult = response.result; state.selectedPath = 0 }
    const text = result.status === 'success'
      ? `${response.facility_name || displayName(result.scenario?.facility_id)} has ${allPaths(result).length} documented path${allPaths(result).length === 1 ? '' : 's'} to ${result.potentially_exposed_products.length} potentially exposed product${result.potentially_exposed_products.length === 1 ? '' : 's'}. This does not establish delay or severity.`
      : result.message || response.message || 'The investigation could not be completed.'
    state.messages.push({ role: 'assistant', text, result: response.result || null, mode: state.dataMode === 'live' ? 'PRECISO live' : 'PRECISO query' })
  } catch (error) {
    state.messages.push({ role: 'assistant', text: `The live backend is unavailable: ${error.message}`, mode: 'Connection error' })
  } finally {
    state.busy = null
    persistConversation()
    render()
    requestAnimationFrame(() => document.querySelector('.conversation-scroll')?.scrollTo({ top: 999999, behavior: 'smooth' }))
  }
}

function useCuratedSample() { state.payload = structuredClone(curatedPayload); state.documents = documentsFromPayload(curatedPayload); state.approvals = new Set(curatedPayload.relationships.map((_, index) => index)); state.queryResult = buildCuratedQuery(curatedPayload); state.dataMode = 'curated_sample'; state.selectedRelationship = 3; state.selectedPath = 0; state.snapshotDate = curatedPayload.snapshot_effective_date; state.notice = 'Curated sample loaded — extraction accuracy is not implied.'; state.error = ''; render() }

function bindEvents() {
  document.querySelectorAll('[data-action="workspace"]').forEach((button) => button.addEventListener('click', () => { state.screen = 'workspace'; render(); checkBackend() })); document.querySelectorAll('[data-action="home"]').forEach((button) => button.addEventListener('click', () => { state.screen = 'home'; render(); window.scrollTo(0, 0) })); document.querySelectorAll('[data-action="toggle-rail"]').forEach((button) => button.addEventListener('click', () => { state.railOpen = !state.railOpen; render() })); document.querySelectorAll('[data-action="upload"]').forEach((button) => button.addEventListener('click', () => document.querySelector('#source-upload')?.click())); document.querySelectorAll('[data-action="extract"]').forEach((button) => button.addEventListener('click', extractDocuments)); document.querySelectorAll('[data-action="ingest"]').forEach((button) => button.addEventListener('click', ingestApproved)); document.querySelectorAll('[data-action="sample"]').forEach((button) => button.addEventListener('click', useCuratedSample)); document.querySelectorAll('[data-action="clear-conversation"]').forEach((button) => button.addEventListener('click', () => { state.messages = []; persistConversation(); render() })); document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => ask(button.dataset.prompt))); document.querySelectorAll('[data-relationship]').forEach((button) => button.addEventListener('click', () => { state.selectedRelationship = Number(button.dataset.relationship); render() })); document.querySelectorAll('[data-path]').forEach((button) => button.addEventListener('click', () => { state.selectedPath = Number(button.dataset.path); render() })); document.querySelectorAll('[data-approval]').forEach((checkbox) => checkbox.addEventListener('change', (event) => { const index = Number(event.target.dataset.approval); event.target.checked ? state.approvals.add(index) : state.approvals.delete(index); render() }))
  document.querySelector('[data-snapshot]')?.addEventListener('change', (event) => { state.snapshotDate = event.target.value })
  document.querySelector('#source-upload')?.addEventListener('change', async (event) => { const files = Array.from(event.target.files || []); const allowed = new Set(['md', 'txt', 'csv', 'json']); const invalid = files.filter((file) => !allowed.has(file.name.split('.').at(-1)?.toLowerCase())); if (invalid.length) { state.error = `Unsupported files: ${invalid.map((file) => file.name).join(', ')}. Use MD, TXT, CSV, or JSON.`; render(); return } state.documents = await Promise.all(files.map(async (file) => ({ name: file.name, content: await file.text(), ext: file.name.split('.').at(-1).toUpperCase(), meta: `${Math.max(1, Math.ceil(file.size / 1024))} KB · ready to extract` }))); state.payload = { document_id: '', snapshot_effective_date: state.snapshotDate, chunks: [], entities: [], relationships: [] }; state.approvals = new Set(); state.queryResult = null; state.dataMode = 'uploaded'; state.notice = `${state.documents.length} document${state.documents.length === 1 ? '' : 's'} ready for Claude extraction.`; state.error = ''; render() })
  const composer = document.querySelector('#composer'); if (composer) { composer.addEventListener('submit', (event) => { event.preventDefault(); const input = composer.elements.message; const value = input.value; input.value = ''; ask(value) }); composer.elements.message.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); composer.requestSubmit() } }) }
}

render()
