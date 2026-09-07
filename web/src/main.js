import './style.css'

const app = document.querySelector('#app')
const steps = [
  ['Thinking', 'Understanding your question'],
  ['Reading documents', 'Reading uploaded source files'],
  ['Extracting relationships', 'Claude is proposing documented entity links'],
  ['Writing preciso_extract.json', 'Creating structured output for PRECISO'],
  ['Sending to PRECISO MCP', 'Validating and ingesting approved relationships'],
  ['Building local graph', 'Querying persisted dependency paths'],
]
const querySteps = [
  ['Thinking', 'Understanding your question'],
  ['Querying PRECISO graph', 'Traversing persisted dependency paths'],
  ['Retrieving evidence', 'Collecting source chunks and references'],
  ['Grounding answer', 'Claude is synthesizing only returned evidence'],
]
const icon = (name, size = 18) => {
  const paths = {
    plus: '<path d="M12 5v14M5 12h14"/>', chat: '<path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.4 8.4 0 0 1-3.7-.8L4 20l1.8-3.6A7.2 7.2 0 0 1 4 11.5 7.5 7.5 0 0 1 12 4a7.5 7.5 0 0 1 8 7.5Z"/>', file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/>', clip: '<path d="m8.5 12.5 5.8-5.8a3 3 0 0 1 4.2 4.2l-7.7 7.7a5 5 0 0 1-7.1-7.1l7.7-7.7a3 3 0 0 1 4.2 4.2l-7.7 7.7a1 1 0 0 0 1.4 1.4l6.7-6.7"/>', arrow: '<path d="M5 12h13M13 6l6 6-6 6"/>', graph: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 11 7.5-4M8.2 13l7.5 4"/>', check: '<path d="m5 12 4 4L19 6"/>',
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ''}</svg>`
}
const escapeHTML = (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;')
const api = async (path, options = {}) => { const response = await fetch(path, { ...options, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) } }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`); return body }
const state = { tab: 'Chat', processing: false, operation: null, step: steps.length, files: [], messages: [], backend: { connected: false, extractor: {} }, error: '', liveResult: null, liveAnswer: '', graphReady: false, extractionPayload: null }
function fileIcon(file) { const type = String(file.type || file.name?.split('.').pop() || 'TXT').toUpperCase(); return `<span class="file-icon file-${type.toLowerCase()}">${type === 'PDF' ? '⌁' : type === 'CSV' ? '▦' : 'MD'}</span>` }
function renderSidebar() {
  const output = state.graphReady ? `<div class="output-item">${icon('file', 20)}<span><b>preciso_extract.json</b><small>Graph created from this session</small></span></div>` : '<p class="sidebar-empty">No outputs yet.</p>'
  const chats = state.messages.length ? '<button class="side-chat selected">' + icon('chat', 17) + '<span>Current session</span></button>' : '<p class="sidebar-empty">No chats yet.</p>'
  const sources = state.files.length ? state.files.map(file => `<div class="source-item">${fileIcon(file)}<span>${escapeHTML(file.name)}</span></div>`).join('') : '<p class="sidebar-empty">No sources uploaded.</p>'
  return `<aside class="sidebar"><div class="sidebar-section"><div class="section-title"><span>Outputs</span><button class="icon-button" aria-label="Add output">${icon('plus', 17)}</button></div>${output}</div><div class="sidebar-section"><div class="section-title"><span>Side chats</span><button class="icon-button" aria-label="New side chat">${icon('plus', 17)}</button></div>${chats}</div><div class="sidebar-section"><div class="section-title"><span>Sources</span><button class="icon-button" data-action="upload" aria-label="Add source">${icon('plus', 17)}</button></div>${sources}${state.files.length ? `<button class="view-sources" data-tab="Sources">${icon('arrow', 16)}<span>View all sources</span></button>` : ''}</div></aside>`
}
function renderTopbar() { return `<header class="topbar"><button class="brand" data-action="home" aria-label="PRECISO Supply Center"><strong>PRECISO</strong><span>Supply Center</span></button><nav class="nav-tabs" aria-label="Primary navigation">${['Chat', 'Sources', 'Graph'].map(tab => `<button class="nav-tab ${state.tab === tab ? 'active' : ''}" data-tab="${tab}">${tab}</button>`).join('')}</nav><div class="top-actions"><span class="connection"><i class="status-dot ${state.backend.connected ? 'online' : ''}"></i><span>${state.backend.connected ? 'MCP Connected' : 'MCP Offline'}</span></span><span class="avatar">JD</span></div></header>` }
function renderFileChips(files) { return files?.length ? `<div class="message-files">${files.map(file => `<span class="message-file">${fileIcon(file)}<span>${escapeHTML(file.name)}</span><button aria-label="Remove ${escapeHTML(file.name)}">×</button></span>`).join('')}</div>` : '' }
function renderProcessing() { const activeSteps = state.operation === 'query' ? querySteps : steps; return `<article class="assistant-card processing-card"><div class="assistant-intro"><span class="agent-mark">✦</span><div><p>${state.operation === 'query' ? 'I’ll query the persisted PRECISO graph and ground the answer in its returned evidence.' : 'I’ll inspect the uploaded documents, validate the extraction, and create the PRECISO graph.'}</p></div></div><div class="timeline">${activeSteps.map(([title, subtext], index) => { const done = index < state.step; const active = index === state.step; return `<div class="timeline-row ${done ? 'done' : ''} ${active ? 'active' : ''}"><span class="timeline-node">${done ? icon('check', 14) : active ? '<i></i>' : ''}</span><div><b>${title}</b><small>${subtext}</small></div><time>${done ? `${[2, 6, 9, 12, 15][index] || 18}s` : active ? 'now' : ''}</time></div>` }).join('')}</div></article>` }
function resultProducts(result) { return result?.potentially_exposed_products || [] }
function renderGrounded(message) { const result = message.result || {}; const products = resultProducts(result); const evidence = products.flatMap(product => (product.paths || []).flatMap(path => path.edges || [])).flatMap(edge => edge.evidence || []); return `<article class="assistant-card completion-card"><div class="assistant-intro"><span class="agent-mark success">${icon('check', 18)}</span><div><h2>PRECISO answer.</h2><p>Claude grounded this answer in persisted graph evidence.</p></div><time>Live</time></div><p class="grounded-answer">${escapeHTML(message.answer || 'No grounded answer returned.')}</p>${products.length ? `<div class="dependency-path">${products.map(product => `<span>${escapeHTML(product.paths?.[0]?.nodes?.map(id => id.split(':').at(-1).replaceAll('-', ' ')).join(' → ') || product.product_id)}</span>`).join('')}</div>` : ''}<p class="completion-copy">${result.completeness?.is_truncated ? 'The result was truncated at the configured path limit.' : `Evidence returned from ${evidence.length} graph edge${evidence.length === 1 ? '' : 's'}${result.snapshot?.document_ids?.length ? ` in ${result.snapshot.document_ids.join(', ')}` : ''}.`}</p><div class="completion-actions"><button class="outline-button" data-tab="Graph">${icon('graph', 17)}View graph <span>→</span></button><button class="outline-button">${icon('file', 17)}Evidence: ${evidence.length}</button></div></article>` }
function renderMessages() { if (!state.messages.length) { const title = state.graphReady ? 'Graph ready.' : state.files.length ? 'Documents ready to build.' : 'No graph or documents to query.'; const copy = state.graphReady ? 'The PRECISO graph is ready. Ask a supply-chain question below.' : state.files.length ? 'Create the graph before asking questions. The agent will not query unindexed documents.' : 'Upload source documents, then create the graph before asking a question.'; return `<div class="empty-thread"><span>${title}</span><p>${copy}</p></div>` } return state.messages.map(message => message.role === 'user' ? `<article class="user-message"><div class="user-bubble"><p>${escapeHTML(message.text)}</p>${renderFileChips(message.files)}</div><time>Live</time></article>` : message.kind === 'result' ? renderGrounded(message) : `<article class="assistant-card"><div class="assistant-intro"><span class="agent-mark">✦</span><p>${escapeHTML(message.text)}</p></div></article>`).join('') }
function renderComposer() { const canBuild = state.files.length > 0 && !state.graphReady && !state.processing; const canQuery = state.graphReady && !state.processing; return `<form class="composer" id="composer"><input id="source-upload" type="file" multiple accept=".md,.txt,.csv,.json" hidden /><button class="attach-button" type="button" data-action="upload" aria-label="Attach source files">${icon('clip', 22)}</button><textarea name="message" rows="1" placeholder="${state.graphReady ? 'Ask a question about the persisted graph...' : 'Upload documents, then create the graph...'}" ${canQuery ? '' : 'disabled'}></textarea><div class="composer-meta"><span class="file-pills"><span>PDF</span><span>CSV</span><span>TXT</span><span>MD</span><span>…</span></span><button class="create-graph-button ${canBuild ? 'visible' : ''}" type="button" data-action="create-graph" ${canBuild ? '' : 'disabled'}>${icon('graph', 15)}Create graph</button><button class="model-button" type="button">${escapeHTML(state.backend.extractor.model || 'Claude Sonnet 5')} <span>⌄</span></button></div><button class="send-button" type="submit" aria-label="Send message" ${canQuery ? '' : 'disabled'}>${icon('arrow', 20)}</button></form>` }
function renderMain() { if (state.tab === 'Sources') return `<div class="tab-surface"><div class="surface-eyebrow">SOURCE LIBRARY</div><h1>Documents in this workspace.</h1><p>Source files are not queryable until you create the PRECISO graph.</p><div class="library-grid">${state.files.length ? state.files.map(file => `<article>${fileIcon(file)}<b>${escapeHTML(file.name)}</b><small>${file.size || 'Ready for graph creation'}</small></article>`).join('') : '<div class="graph-path"><span>No sources uploaded yet.</span></div>'}</div></div>`; if (state.tab === 'Graph') { const products = resultProducts(state.liveResult); return `<div class="tab-surface graph-surface"><div class="surface-eyebrow">PRECISO GRAPH</div><h1>Dependency paths.</h1><p>${state.graphReady ? state.liveResult ? 'Persisted relationships returned by PRECISO.' : 'Graph created. Ask a question to inspect dependency paths.' : 'No graph has been created for this session.'}</p>${products.length ? products.flatMap(product => product.paths || []).map(path => `<div class="graph-path">${path.nodes.map(id => `<span>${escapeHTML(id.split(':').at(-1).replaceAll('-', ' '))}</span>`).join('<i>→</i>')}</div>`).join('') : '<div class="graph-path"><span>No queried paths yet.</span></div>'}<button class="outline-button" data-tab="Chat">${icon('arrow', 17)}Back to chat</button></div>` } return `<section class="chat-main"><div class="conversation-scroll"><div class="chat-heading"><div class="eyebrow">SUPPLY-CHAIN INTELLIGENCE</div><h1>Ask what depends on what.</h1><p>Upload sources, create a PRECISO graph, then query only persisted evidence.</p></div>${state.error ? `<div class="error-strip">${escapeHTML(state.error)}</div>` : ''}<div class="conversation">${renderMessages()}${state.processing ? renderProcessing() : ''}</div></div>${renderComposer()}</section>` }
function render() { app.innerHTML = `<main class="app-shell">${renderTopbar()}<div class="workspace"><div class="sidebar-wrap">${renderSidebar()}</div>${renderMain()}</div></main>`; bindEvents() }
function setStep(step) { state.step = step; render() }
function sourceDocuments() { return state.files.filter(file => file.content).map(file => ({ name: file.name, content: file.content })) }
async function runGraphBuild() {
  const documents = sourceDocuments()
  if (!documents.length) throw new Error('Attach at least one MD, TXT, CSV, or JSON source file before creating the graph.')
  setStep(1)
  const extraction = await api('/api/extract', { method: 'POST', body: JSON.stringify({ snapshot_effective_date: new Date().toISOString().slice(0, 10), documents }) })
  setStep(3)
  setStep(4)
  const ingest = await api('/api/ingest', { method: 'POST', body: JSON.stringify({ approved: true, payload: extraction.payload }) })
  if (ingest.status !== 'success') throw new Error(ingest.errors?.join('; ') || ingest.message || 'PRECISO rejected the extraction.')
  setStep(5)
  state.extractionPayload = extraction.payload
  state.graphReady = true
  state.liveResult = null
  state.messages.push({ role: 'assistant', kind: 'graph-ready', text: `Graph created. ${ingest.relationships_merged || extraction.payload.relationships?.length || 0} relationships are now persisted in PRECISO.` })
  state.processing = false; state.operation = null; state.step = steps.length; render()
}
async function runQuery(question) {
  setStep(0)
  const facilities = (state.extractionPayload?.entities || []).filter(entity => entity.entity_type === 'FACILITY')
  const normalizedQuestion = question.toLowerCase()
  const matchingFacilities = facilities.filter(facility => {
    const id = String(facility.entity_name || '').toLowerCase()
    const label = id.split(':').at(-1).replaceAll('-', ' ')
    return normalizedQuestion.includes(id) || normalizedQuestion.includes(label)
  })
  const facility = matchingFacilities.length === 1 ? matchingFacilities[0] : facilities.length === 1 ? facilities[0] : null
  if (!facility) throw new Error('Name exactly one facility from the uploaded documents so PRECISO can query the correct path.')
  setStep(1)
  const investigation = await api('/api/investigate', { method: 'POST', body: JSON.stringify({ facility_id: facility.entity_name, max_paths: 100 }) })
  if (investigation.status !== 'success') throw new Error(investigation.message || 'PRECISO query failed.')
  setStep(2)
  const grounded = await api('/api/grounded-answer', { method: 'POST', body: JSON.stringify({ question, investigation }) })
  setStep(3)
  state.liveResult = investigation
  state.liveAnswer = grounded.answer
  state.messages.push({ role: 'assistant', kind: 'result', answer: grounded.answer, result: investigation })
  state.processing = false; state.operation = null; state.step = querySteps.length; render()
}
async function startGraphBuild() { state.processing = true; state.operation = 'build'; state.step = 0; state.error = ''; render(); try { await runGraphBuild() } catch (error) { state.processing = false; state.operation = null; state.error = error.message; render() } }
async function startQuery(question) { state.messages.push({ role: 'user', text: question, files: [] }); state.processing = true; state.operation = 'query'; state.step = 0; state.error = ''; render(); try { await runQuery(question) } catch (error) { state.processing = false; state.operation = null; state.error = error.message; render() } }
async function checkBackend() { try { const status = await api('/api/status'); state.backend.connected = status.engine?.overall !== 'error'; state.backend.extractor = status.extractor || {}; } catch { state.backend.connected = false } render() }
function bindEvents() { document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; render() })); document.querySelectorAll('[data-action="upload"]').forEach(button => button.addEventListener('click', () => document.querySelector('#source-upload')?.click())); document.querySelector('[data-action="create-graph"]')?.addEventListener('click', startGraphBuild); document.querySelector('#source-upload')?.addEventListener('change', async event => { const files = Array.from(event.target.files || []); state.files = await Promise.all(files.map(async file => ({ name: file.name, type: file.name.split('.').pop().toUpperCase(), size: `${Math.max(1, Math.ceil(file.size / 1024))} KB`, content: await file.text() }))); state.graphReady = false; state.extractionPayload = null; state.liveResult = null; state.tab = 'Chat'; state.error = ''; render() }); document.querySelector('#composer')?.addEventListener('submit', event => { event.preventDefault(); const input = event.currentTarget.elements.message; const question = input.value.trim(); if (!question || state.processing || !state.graphReady) return; input.value = ''; startQuery(question) }); document.querySelector('.brand')?.addEventListener('click', () => { state.tab = 'Chat'; render() }) }
render(); checkBackend()
