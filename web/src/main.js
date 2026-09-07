import DOMPurify from 'dompurify'
import { marked } from 'marked'
import './style.css'

const app = document.querySelector('#app')
const icon = (name, size = 18) => {
  const paths = {
    plus: '<path d="M12 5v14M5 12h14"/>',
    chat: '<path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.4 8.4 0 0 1-3.7-.8L4 20l1.8-3.6A7.2 7.2 0 0 1 4 11.5 7.5 7.5 0 0 1 12 4a7.5 7.5 0 0 1 8 7.5Z"/>',
    file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/>',
    clip: '<path d="m8.5 12.5 5.8-5.8a3 3 0 0 1 4.2 4.2l-7.7 7.7a5 5 0 0 1-7.1-7.1l7.7-7.7a3 3 0 0 1 4.2 4.2l-7.7 7.7a1 1 0 0 0 1.4 1.4l6.7-6.7"/>',
    arrow: '<path d="M5 12h13M13 6l6 6-6 6"/>',
    graph: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 11 7.5-4M8.2 13l7.5 4"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ''}</svg>`
}
const escapeHTML = (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;')
const renderMarkdown = (value) => DOMPurify.sanitize(marked.parse(String(value ?? ''), { gfm: true, breaks: true }))
const api = async (path, options = {}) => {
  const response = await fetch(path, { ...options, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body
}

const state = {
  tab: 'Chat', processing: false, files: [], messages: [],
  backend: { connected: false, extractor: {} }, error: '', graphReady: false,
  threadId: null, run: null, events: [], eventSource: null,
}

function fileIcon(file) {
  const type = String(file.type || file.name?.split('.').pop() || 'TXT').toUpperCase()
  return `<span class="file-icon file-${type.toLowerCase()}">${type === 'CSV' ? '▦' : type === 'JSON' ? '{}' : 'MD'}</span>`
}

function renderSidebar() {
  const outputs = Object.values(state.run?.state?.extraction_results || {})
  const output = outputs.length ? outputs.map(item => `<a class="output-item" href="${escapeHTML(item.artifact_url || '#')}" download>${icon('file', 20)}<span><b>${escapeHTML(item.artifact_name || 'extraction.json')}</b><small>Independent source artifact · download</small></span></a>`).join('') : '<p class="sidebar-empty">No outputs yet.</p>'
  const chats = state.messages.length ? '<button class="side-chat selected">' + icon('chat', 17) + '<span>Current session</span></button>' : '<p class="sidebar-empty">No chats yet.</p>'
  const sources = state.files.length ? state.files.map(file => `<div class="source-item">${fileIcon(file)}<span>${escapeHTML(file.name)}</span></div>`).join('') : '<p class="sidebar-empty">No sources uploaded.</p>'
  return `<aside class="sidebar"><div class="sidebar-section"><div class="section-title"><span>Outputs</span></div>${output}</div><div class="sidebar-section"><div class="section-title"><span>Side chats</span></div>${chats}</div><div class="sidebar-section"><div class="section-title"><span>Sources</span><button class="icon-button" data-action="upload" aria-label="Add source">${icon('plus', 17)}</button></div>${sources}${state.files.length ? `<button class="view-sources" data-tab="Sources">${icon('arrow', 16)}<span>View all sources</span></button>` : ''}</div></aside>`
}

function renderTopbar() {
  return `<header class="topbar"><button class="brand" data-action="home" aria-label="PRECISO Supply Center"><strong>PRECISO</strong><span>Supply Center</span></button><nav class="nav-tabs" aria-label="Primary navigation">${['Chat', 'Sources', 'Graph'].map(tab => `<button class="nav-tab ${state.tab === tab ? 'active' : ''}" data-tab="${tab}">${tab}</button>`).join('')}</nav><div class="top-actions"><span class="connection"><i class="status-dot ${state.backend.connected ? 'online' : ''}"></i><span>${state.backend.connected ? 'MCP Connected' : 'MCP Offline'}</span></span><span class="avatar">JD</span></div></header>`
}

function renderFileChips(files) {
  return files?.length ? `<div class="message-files">${files.map(file => `<span class="message-file">${fileIcon(file)}<span>${escapeHTML(file.name)}</span></span>`).join('')}</div>` : ''
}

const eventLabels = {
  'run.started': 'Run started', 'preciso.status.completed': 'PRECISO status checked',
  'source.read.completed': 'Source read', 'extraction.completed': 'Extraction created',
  'extraction.artifact_written': 'Extraction artifact written', 'validation.completed': 'Extraction validated',
  'extraction.validation_failed': 'Validation issue found', 'extraction.repair.started': 'Repairing extraction',
  'extraction.patch.generated': 'Minimal repair generated', 'extraction.edit.started': 'Updating extraction artifact',
  'extraction.edit.completed': 'Extraction artifact updated', 'extraction.revalidation.started': 'Revalidating extraction',
  'extraction.revalidation.completed': 'Revalidation completed', 'extraction.repair.completed': 'Extraction repaired',
  'approval.required': 'Approval required',
  'approval.received': 'Approval received', 'ingestion.completed': 'Ingestion completed',
  'graph.query.completed': 'PRECISO graph queried', 'answer.started': 'Grounded answer started',
  'answer.completed': 'Grounded answer completed',
}
function renderExecution() {
  const visible = state.events.filter(event => eventLabels[event.type])
  if (!visible.length) return ''
  return `<div class="timeline execution-timeline">${visible.slice(-18).map(event => {
    const marker = event.type.includes('failed') ? '×' : event.type.endsWith('.started') ? '↻' : icon('check', 14)
    return `<div class="timeline-row done"><span class="timeline-node">${marker}</span><div><b>${escapeHTML(eventLabels[event.type])}</b><small>${escapeHTML(event.source_name || event.data?.artifact_name || '')}</small></div><time>${escapeHTML(new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</time></div>`
  }).join('')}</div>`
}

function renderApproval() {
  if (!state.run?.awaiting_approval) return ''
  const sources = state.run.interrupts?.[0]?.sources || []
  return `<article class="assistant-card processing-card approval-card"><div class="assistant-intro"><span class="agent-mark">✦</span><div><p>Validated extraction artifacts are ready. Review each independent source before additive ingestion.</p></div></div><div class="approval-list">${sources.map(source => `<div><b>${escapeHTML(source.source_name)}</b><small>${escapeHTML(source.artifact_name)} · ${source.entities} entities · ${source.relationships} relationships · validated</small></div>`).join('')}</div><div class="completion-actions"><button class="outline-button approve-button" data-action="approve">${icon('check', 17)}Approve &amp; build graph</button><button class="outline-button" data-action="reject">Reject</button></div></article>`
}

function resultMessage() {
  if (!state.run?.answer) return ''
  const evidence = state.run.state?.evidence || []
  const extractionOnly = state.run.intent === 'new_sources'
  const heading = extractionOnly ? 'Extraction complete.' : 'PRECISO answer.'
  const description = extractionOnly ? 'The approved source artifacts are now persisted in PRECISO.' : 'Claude grounded this answer in persisted graph evidence.'
  const completionCopy = extractionOnly ? 'No graph question was requested.' : evidence.length ? `Evidence returned from ${evidence.length} PRECISO evidence item${evidence.length === 1 ? '' : 's'}.` : 'The graph returned no directly citable evidence items.'
  return `<article class="assistant-card completion-card"><div class="assistant-intro"><span class="agent-mark success">${icon('check', 18)}</span><div><h2>${heading}</h2><p>${description}</p></div><time>Live</time></div><div class="grounded-answer markdown-content">${renderMarkdown(state.run.answer)}</div><p class="completion-copy">${completionCopy}</p><div class="completion-actions"><button class="outline-button" data-tab="Graph">${icon('graph', 17)}View graph <span>→</span></button></div></article>`
}

function renderMessages() {
  if (!state.messages.length) {
    const title = state.graphReady ? 'Graph ready.' : state.files.length ? 'Documents ready.' : 'Start with a question or source documents.'
    return `<div class="empty-thread"><span>${title}</span><p>${state.graphReady ? 'Ask a supply-chain question about persisted PRECISO knowledge.' : 'Upload source documents and ask one question; the agent will extract, validate, pause for approval, then query PRECISO.'}</p></div>`
  }
  const liveAnswer = state.processing && state.run?.answer ? resultMessage() : ''
  return state.messages.map(message => message.role === 'user' ? `<article class="user-message"><div class="user-bubble"><p>${escapeHTML(message.text)}</p>${renderFileChips(message.files)}</div><time>Live</time></article>` : '').join('') + (state.processing ? `<article class="assistant-card processing-card"><div class="assistant-intro"><span class="agent-mark">✦</span><p>The LangGraph run is executing and its checkpointed events are streaming below.</p></div>${renderExecution()}</article>${liveAnswer}` : renderApproval() + resultMessage())
}

function renderComposer() {
  const canSubmit = !state.processing && (state.graphReady || state.files.length > 0)
  return `<form class="composer" id="composer"><input id="source-upload" type="file" multiple accept=".md,.txt,.csv,.json" hidden /><button class="attach-button" type="button" data-action="upload" aria-label="Attach source files">${icon('clip', 22)}</button><textarea name="message" rows="1" placeholder="${state.files.length ? 'Ask a question about these sources...' : 'Ask a question about the persisted graph...'}" ${canSubmit ? '' : 'disabled'}></textarea><div class="composer-meta"><span class="file-pills"><span>CSV</span><span>TXT</span><span>MD</span><span>JSON</span></span><button class="model-button" type="button">${escapeHTML(state.backend.extractor.model || 'Claude')} <span>⌄</span></button></div><button class="send-button" type="submit" aria-label="Send message" ${canSubmit ? '' : 'disabled'}>${icon('arrow', 20)}</button></form>`
}

function renderMain() {
  if (state.tab === 'Sources') return `<div class="tab-surface"><div class="surface-eyebrow">SOURCE LIBRARY</div><h1>Documents in this workspace.</h1><p>Each source receives an independent extraction artifact and review status.</p><div class="library-grid">${state.files.length ? state.files.map(file => `<article>${fileIcon(file)}<b>${escapeHTML(file.name)}</b><small>${file.size || 'Ready for graph creation'}</small></article>`).join('') : '<div class="graph-path"><span>No sources uploaded yet.</span></div>'}</div></div>`
  if (state.tab === 'Graph') return `<div class="tab-surface graph-surface"><div class="surface-eyebrow">PRECISO GRAPH</div><h1>Persisted dependency paths.</h1><p>${state.graphReady ? 'Relationships returned by PRECISO are the only graph-grounded context used for answers.' : 'No graph has been created for this session.'}</p><div class="graph-path"><span>${state.graphReady ? 'Query the graph from Chat to inspect returned paths.' : 'No queried paths yet.'}</span></div><button class="outline-button" data-tab="Chat">${icon('arrow', 17)}Back to chat</button></div>`
  return `<section class="chat-main"><div class="conversation-scroll"><div class="chat-heading"><div class="eyebrow">SUPPLY-CHAIN INTELLIGENCE</div><h1>Ask what depends on what.</h1><p>LangGraph coordinates sources, approval, PRECISO graph truth, evidence, and grounded answers.</p></div>${state.error ? `<div class="error-strip">${escapeHTML(state.error)}</div>` : ''}<div class="conversation">${renderMessages()}</div></div>${renderComposer()}</section>`
}

function render() {
  app.innerHTML = `<main class="app-shell">${renderTopbar()}<div class="workspace"><div class="sidebar-wrap">${renderSidebar()}</div>${renderMain()}</div></main>`
  bindEvents()
}

function consumeRun(run) {
  state.run = run
  state.threadId = run.thread_id
  if (run.events) state.events = run.events
  state.graphReady = Object.values(run.state?.ingestion_results || {}).some(item => item.status === 'success') || Object.values(run.state?.source_statuses || {}).some(status => status === 'ingested')
  state.processing = run.status === 'running'
  state.error = run.status === 'failed' ? (run.state?.errors || []).join('; ') : ''
  render()
}

function openEventStream(run) {
  if (state.eventSource) state.eventSource.close()
  if (!run.events_url) return
  state.eventSource = new EventSource(run.events_url)
  state.eventSource.addEventListener('answer.token', event => {
    const text = JSON.parse(event.data).data?.text
    if (typeof text !== 'string') return
    state.run = { ...(state.run || {}), answer: text }
    render()
  })
  Object.keys(eventLabels).forEach(type => state.eventSource.addEventListener(type, event => {
    const next = JSON.parse(event.data)
    if (!state.events.some(existing => existing.timestamp === next.timestamp && existing.type === next.type)) state.events.push(next)
    render()
  }))
  state.eventSource.addEventListener('run.failed', event => {
    const next = JSON.parse(event.data)
    state.events.push(next)
    state.processing = false
    state.error = next.data?.error || 'Run failed'
    state.eventSource?.close()
    render()
  })
  state.eventSource.addEventListener('run.status', async event => {
    const status = JSON.parse(event.data).data?.status
    if (!['awaiting_approval', 'completed', 'failed'].includes(status) || !state.threadId) return
    try {
      const snapshot = await api(`/api/runs/${encodeURIComponent(state.threadId)}`)
      consumeRun(snapshot)
    } catch (error) {
      state.processing = false
      state.error = error.message
      render()
    }
    if (status !== 'awaiting_approval') state.eventSource?.close()
  })
}

async function startRun(question) {
  const files = state.files
  state.messages.push({ role: 'user', text: question, files })
  state.processing = true
  state.error = ''
  render()
  try {
    const run = await api('/api/runs', { method: 'POST', body: JSON.stringify({ message: question, conversation_id: state.threadId, snapshot_effective_date: new Date().toISOString().slice(0, 10), ...(files.length ? { source_ids: files.map(file => file.source_id) } : {}) }) })
    state.events = []
    consumeRun(run)
    openEventStream(run)
  } catch (error) {
    state.processing = false
    state.error = error.message
    render()
  }
}

async function approveRun(approved = true) {
  if (!state.threadId) return
  state.processing = true
  state.error = ''
  render()
  try {
    const run = await api(`/api/runs/${encodeURIComponent(state.threadId)}/approval`, { method: 'POST', body: JSON.stringify({ approved }) })
    consumeRun(run)
    openEventStream(run)
  } catch (error) {
    state.processing = false
    state.error = error.message
    render()
  }
}

async function checkBackend() {
  try {
    const status = await api('/api/status')
    state.backend.connected = ['ready', 'degraded'].includes(status.engine?.overall)
    state.backend.extractor = status.extractor || {}
  } catch {
    state.backend.connected = false
  }
  render()
}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; render() }))
  document.querySelectorAll('[data-action="upload"]').forEach(button => button.addEventListener('click', () => document.querySelector('#source-upload')?.click()))
  document.querySelector('[data-action="approve"]')?.addEventListener('click', () => approveRun(true))
  document.querySelector('[data-action="reject"]')?.addEventListener('click', () => approveRun(false))
  document.querySelector('#source-upload')?.addEventListener('change', async event => {
    const files = Array.from(event.target.files || [])
    try {
      const documents = await Promise.all(files.map(async file => ({ name: file.name, content: await file.text() })))
      const uploaded = await api('/api/sources', { method: 'POST', body: JSON.stringify(documents) })
      state.files = uploaded.sources.map(source => ({ ...source, type: source.extension.slice(1).toUpperCase(), size: `${Math.max(1, Math.ceil(source.size / 1024))} KB` }))
    } catch (error) {
      state.error = error.message
      render()
      return
    }
    state.graphReady = false
    state.run = null
    state.events = []
    state.tab = 'Chat'
    state.error = ''
    render()
  })
  document.querySelector('#composer')?.addEventListener('submit', event => {
    event.preventDefault()
    const input = event.currentTarget.elements.message
    const question = input.value.trim() || (state.files.length ? 'Build the graph from these source documents.' : '')
    if (!question || state.processing || (!state.graphReady && !state.files.length)) return
    input.value = ''
    startRun(question)
  })
  document.querySelector('.brand')?.addEventListener('click', () => { state.tab = 'Chat'; render() })
}

render()
checkBackend()
