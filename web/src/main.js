import './style.css'

const app = document.querySelector('#app')
const STORAGE_KEY = 'preciso-supply-center-chat-v1'
const demoFiles = [
  { name: 'supplier_report.pdf', type: 'PDF', size: '12 MB' },
  { name: 'bom.csv', type: 'CSV', size: '890 KB' },
  { name: 'sourcing_notes.md', type: 'MD', size: '46 KB' },
]
const steps = [
  ['Thinking', 'Understanding your question'],
  ['Reading documents', 'supplier_report.pdf, bom.csv, sourcing_notes.md'],
  ['Extracting relationships', 'Identifying facility → component → product links'],
  ['Writing preciso_extract.json', 'Creating structured output for PRECISO'],
  ['Sending to PRECISO MCP', 'Ingesting extracted relationships'],
  ['Building local graph', 'Updating network with new relationships'],
]
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
function loadMessages() { try { const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); return Array.isArray(saved) ? saved : [] } catch { return [] } }
const initialMessages = [{ role: 'user', text: 'What products depend on the Apex Components facility?', files: demoFiles }, { role: 'assistant', kind: 'complete' }]
const state = { tab: 'Chat', processing: false, step: steps.length, files: demoFiles, messages: loadMessages().length ? loadMessages() : initialMessages, backend: { connected: true }, error: '' }
function persist() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.messages.slice(-30))) }
function fileIcon(file) { const type = String(file.type || file.name?.split('.').pop() || 'TXT').toUpperCase(); return `<span class="file-icon file-${type.toLowerCase()}">${type === 'PDF' ? '⌁' : type === 'CSV' ? '▦' : 'MD'}</span>` }
function renderSidebar() {
  const sources = state.files.length ? state.files : demoFiles
  return `<aside class="sidebar"><div class="sidebar-section"><div class="section-title"><span>Outputs</span><button class="icon-button" aria-label="Add output">${icon('plus', 17)}</button></div><div class="output-item">${icon('file', 20)}<span><b>preciso_extract.json</b><small>Added just now</small></span></div></div><div class="sidebar-section"><div class="section-title"><span>Side chats</span><button class="icon-button" aria-label="New side chat">${icon('plus', 17)}</button></div>${['Apex Components dep...', 'Tier 2 suppliers', 'Facility risk analysis', 'New chat'].map((item, i) => `<button class="side-chat ${i === 0 ? 'selected' : ''}">${icon('chat', 17)}<span>${item}</span></button>`).join('')}</div><div class="sidebar-section"><div class="section-title"><span>Sources</span><button class="icon-button" data-action="upload" aria-label="Add source">${icon('plus', 17)}</button></div>${sources.map(file => `<div class="source-item">${fileIcon(file)}<span>${escapeHTML(file.name)}</span></div>`).join('')}<button class="view-sources" data-tab="Sources">${icon('arrow', 16)}<span>View all sources</span></button></div></aside>`
}
function renderTopbar() { return `<header class="topbar"><button class="brand" data-action="home" aria-label="PRECISO Supply Center"><strong>PRECISO</strong><span>Supply Center</span></button><nav class="nav-tabs" aria-label="Primary navigation">${['Chat', 'Sources', 'Graph'].map(tab => `<button class="nav-tab ${state.tab === tab ? 'active' : ''}" data-tab="${tab}">${tab}</button>`).join('')}</nav><div class="top-actions"><span class="connection"><i class="status-dot ${state.backend.connected ? 'online' : ''}"></i><span>${state.backend.connected ? 'MCP Connected' : 'MCP Offline'}</span></span><span class="avatar">JD</span></div></header>` }
function renderFileChips(files) { return files?.length ? `<div class="message-files">${files.map(file => `<span class="message-file">${fileIcon(file)}<span>${escapeHTML(file.name)}</span><button aria-label="Remove ${escapeHTML(file.name)}">×</button></span>`).join('')}</div>` : '' }
function renderProcessing() { return `<article class="assistant-card processing-card"><div class="assistant-intro"><span class="agent-mark">✦</span><div><p>I’ll analyze your documents to find what products depend on the Apex Components facility. Let me extract the relationships and update the local graph.</p></div></div><div class="timeline">${steps.map(([title, subtext], index) => { const done = index < state.step; const active = index === state.step; return `<div class="timeline-row ${done ? 'done' : ''} ${active ? 'active' : ''}"><span class="timeline-node">${done ? icon('check', 14) : active ? '<i></i>' : ''}</span><div><b>${title}</b><small>${subtext}</small></div><time>${done ? `${[2, 6, 9, 12, 15][index] || 18}s` : active ? 'now' : ''}</time></div>` }).join('')}</div></article>` }
function renderCompletion() { return `<article class="assistant-card completion-card"><div class="assistant-intro"><span class="agent-mark success">${icon('check', 18)}</span><div><h2>Extraction complete.</h2><p>4 relationships added to the local graph.</p></div><time>Today, 10:24 AM</time></div><div class="dependency-path"><span>Apex Components</span><b>→</b><span>Control Board X2</span><b>→</b><span>AquaPump 300 / AquaPump 500</span></div><p class="completion-copy">A PRECISO extractable file (<a href="#sources">preciso_extract.json</a>) has been created and added to your Sources.</p><div class="completion-actions"><button class="outline-button" data-tab="Graph">${icon('graph', 17)}View graph <span>→</span></button><button class="outline-button">${icon('file', 17)}Evidence: 4</button><span class="added-badge">${icon('file', 16)}preciso_extract.json added to Sources</span></div></article>` }
function renderMessages() { return state.messages.map(message => message.role === 'user' ? `<article class="user-message"><div class="user-bubble"><p>${escapeHTML(message.text)}</p>${renderFileChips(message.files)}</div><time>Today, 10:24 AM</time></article>` : message.kind === 'complete' ? renderCompletion() : `<article class="assistant-card"><div class="assistant-intro"><span class="agent-mark">✦</span><p>${escapeHTML(message.text)}</p></div></article>`).join('') }
function renderComposer() { return `<form class="composer" id="composer"><input id="source-upload" type="file" multiple accept=".pdf,.csv,.txt,.md" hidden /><button class="attach-button" type="button" data-action="upload" aria-label="Attach source files">${icon('clip', 22)}</button><textarea name="message" rows="1" placeholder="Drop source files here or ask a supply-chain question..."></textarea><div class="composer-meta"><span class="file-pills"><span>PDF</span><span>CSV</span><span>TXT</span><span>MD</span><span>…</span></span><button class="model-button" type="button">Claude Sonnet 5 <span>⌄</span></button></div><button class="send-button" type="submit" aria-label="Send message">${icon('arrow', 20)}</button></form>` }
function renderMain() {
  if (state.tab === 'Sources') return `<div class="tab-surface"><div class="surface-eyebrow">SOURCE LIBRARY</div><h1>Documents in this workspace.</h1><p>Source files stay available to the agent and are used to ground every extraction.</p><div class="library-grid">${state.files.map(file => `<article>${fileIcon(file)}<b>${escapeHTML(file.name)}</b><small>${file.size || 'Ready for analysis'}</small></article>`).join('')}</div></div>`
  if (state.tab === 'Graph') return `<div class="tab-surface graph-surface"><div class="surface-eyebrow">PRECISO GRAPH</div><h1>Dependency paths.</h1><p>Persisted relationships currently connect the Apex Components facility to two products.</p><div class="graph-path"><span>APEX COMPONENTS</span><i>→</i><span>CONTROL BOARD X2</span><i>→</i><span>AQUAPUMP 300 / 500</span></div><button class="outline-button" data-tab="Chat">${icon('arrow', 17)}Back to chat</button></div>`
  return `<section class="chat-main"><div class="conversation-scroll"><div class="chat-heading"><div class="eyebrow">SUPPLY-CHAIN INTELLIGENCE</div><h1>Ask what depends on what.</h1><p>Investigate supply chains with source-backed extraction and PRECISO graph evidence.</p></div>${state.error ? `<div class="error-strip">${escapeHTML(state.error)}</div>` : ''}<div class="conversation">${renderMessages()}${state.processing ? renderProcessing() : ''}</div></div>${renderComposer()}</section>`
}
function render() { app.innerHTML = `<main class="app-shell">${renderTopbar()}<div class="workspace"><div class="sidebar-wrap">${renderSidebar()}</div>${renderMain()}</div></main>`; bindEvents() }
function startProcessing(question, files) { state.messages.push({ role: 'user', text: question, files }); state.processing = true; state.step = 0; state.error = ''; persist(); render(); const timer = setInterval(() => { if (!state.processing) return clearInterval(timer); state.step += 1; if (state.step > steps.length) { state.processing = false; state.messages.push({ role: 'assistant', kind: 'complete' }); persist(); clearInterval(timer) } render() }, 720) }
function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; render() }))
  document.querySelectorAll('[data-action="upload"]').forEach(button => button.addEventListener('click', () => document.querySelector('#source-upload')?.click()))
  document.querySelector('#source-upload')?.addEventListener('change', async event => { const files = Array.from(event.target.files || []); state.files = [...state.files, ...files.map(file => ({ name: file.name, type: file.name.split('.').pop().toUpperCase(), size: `${Math.max(1, Math.ceil(file.size / 1024))} KB` }))]; state.tab = 'Chat'; render() })
  document.querySelector('#composer')?.addEventListener('submit', event => { event.preventDefault(); const input = event.currentTarget.elements.message; const question = input.value.trim(); if (!question || state.processing) return; input.value = ''; startProcessing(question, state.files) })
  document.querySelector('.brand')?.addEventListener('click', () => { state.tab = 'Chat'; render() })
}
render()
