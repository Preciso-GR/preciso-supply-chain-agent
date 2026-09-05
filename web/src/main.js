import './style.css'
import productMark from './assets/supply-center-mark.svg'

const app = document.querySelector('#app')
let disposeOrbitScene = null
let orbitLoadToken = 0

const fixtures = {
  documents: [
    { name: 'facility_register.md', kind: 'Facility register', meta: '3 facilities · 2026-01-15' },
    { name: 'product_bom.md', kind: 'Product bill of materials', meta: '3 components · 2026-01-15' },
    { name: 'identity_notice.md', kind: 'Identity notice', meta: '1 unresolved label · 2026-01-15' },
  ],
  approvals: [
    { id: 1, fact: 'Northbridge Fabrication Facility manufactures Control Unit C-17', type: 'MANUFACTURES', source: 'facility_001', status: 'Validated' },
    { id: 2, fact: 'Control Unit C-17 is used in AquaPump 300', type: 'USED_IN', source: 'bom_001', status: 'Validated' },
    { id: 3, fact: 'Control Unit C-17 is used in AquaPump 500', type: 'USED_IN', source: 'bom_001', status: 'Validated' },
    { id: 4, fact: 'Lakeside Power Module Facility manufactures Power Module P-9', type: 'MANUFACTURES', source: 'facility_002', status: 'Validated' },
    { id: 5, fact: 'Power Module P-9 is used in AquaPump 500', type: 'USED_IN', source: 'bom_002', status: 'Validated' },
  ],
  paths: [
    { product: 'AquaPump 300', component: 'Control Unit C-17', source: 'facility_register.md + product_bom.md', confidence: 'Direct', tone: 'blue' },
    { product: 'AquaPump 500', component: 'Control Unit C-17', source: 'facility_register.md + product_bom.md', confidence: 'Direct', tone: 'violet' },
  ],
  evidence: {
    'facility_register.md': { chunk: 'facility_001', primary: 'Northbridge Fabrication Facility manufactures Control Unit C-17.', secondary: 'In this snapshot, “Northbridge Site” refers to that same facility.' },
    'product_bom.md': { chunk: 'bom_001', primary: 'Control Unit C-17 is used in AquaPump 300 and AquaPump 500.', secondary: 'These are the documented product dependencies for C-17 in this snapshot.' },
    'identity_notice.md': { chunk: 'identity_001', primary: '“Plant 7” is not an alias for a documented canonical facility.', secondary: 'The ambiguous label must remain unresolved.' },
  },
}

let state = {
  screen: 'home',
  selectedSource: 'facility_register.md',
  selectedPath: 0,
  approvals: new Set(fixtures.approvals.map((fact) => fact.id)),
  messages: [],
  backendMode: 'checking',
  inspectorOpen: true,
}

function escapeHTML(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function icon(text, label = '') {
  return `<span class="icon" aria-hidden="true">${text}</span>${label ? `<span>${label}</span>` : ''}`
}

function render() {
  orbitLoadToken += 1
  const currentOrbitToken = orbitLoadToken
  if (disposeOrbitScene) {
    disposeOrbitScene()
    disposeOrbitScene = null
  }
  app.innerHTML = state.screen === 'home' ? renderHome() : renderWorkspace()
  bindEvents()
  const orbitContainer = document.querySelector('#saturn-orbit-scene')
  if (orbitContainer) {
    import('./orbit-scene.js').then(({ createOrbitScene }) => {
      if (currentOrbitToken === orbitLoadToken && orbitContainer.isConnected) {
        disposeOrbitScene = createOrbitScene(orbitContainer)
      }
    }).catch(() => {
      if (currentOrbitToken === orbitLoadToken && orbitContainer.isConnected) {
        orbitContainer.innerHTML = `<img class="orbit-fallback" src="${productMark}" alt="SUPPLY CENTER dependency-path mark" />`
      }
    })
  }
}

function renderHome() {
  return `
    <main class="site-shell home-shell">
      <div class="ambient ambient-one"></div>
      <div class="ambient ambient-two"></div>
      <header class="site-nav">
        <button class="brand" data-action="home" aria-label="SUPPLY CENTER home">
          <img class="brand-logo" src="${productMark}" alt="" width="56" height="56" />
          <span class="brand-copy"><strong>SUPPLY CENTER</strong><small>powered by PRECISO</small></span>
        </button>
        <nav class="nav-links" aria-label="Primary navigation">
          <a href="#product"><span>01</span> Overview</a><a href="#workflow"><span>02</span> Build the graph</a><a href="#evidence"><span>03</span> Trace evidence</a>
        </nav>
        <div class="nav-actions"><button class="small-cta" data-action="workspace">Open center <span aria-hidden="true">↗</span></button></div>
      </header>

      <section class="hero" id="product">
        <div class="hero-copy">
          <p class="eyebrow"><span class="eyebrow-dot"></span> Evidence-first supply intelligence</p>
          <h1>See the paths<br /><em>before they break.</em></h1>
          <p class="hero-lede">SUPPLY CENTER turns messy supply-chain documents into a living, reviewable map of facilities, components, and products — with every answer anchored to source evidence.</p>
          <div class="hero-actions"><button class="primary-cta" data-action="workspace">Get started <span>→</span></button><a class="secondary-cta" href="#workflow">See how it works <span>↓</span></a></div>
          <div class="hero-proof"><span class="proof-line"></span><span>Built for the moment a dependency becomes a decision.</span></div>
        </div>
        <div class="hero-visual" aria-label="Animated dependency network">
          <div id="saturn-orbit-scene" class="orbit-scene" role="img" aria-label="Animated supply dependency network"></div>
          <div class="orbit-caption"><span class="pulse"></span><span>Northbridge · sample snapshot</span><strong>01.15.26</strong></div>
        </div>
      </section>

      <section class="ticker" aria-label="SUPPLY CENTER capabilities"><span>FACILITY GRAPH</span><i></i><span>DOCUMENT EXTRACTION</span><i></i><span>DEPENDENCY PATHS</span><i></i><span>TRACEABLE EVIDENCE</span></section>

      <section class="feature-section" id="workflow">
        <div class="section-heading"><p class="eyebrow">One center, three moves</p><h2>From source files<br /><span>to confident action.</span></h2><p>Keep the analyst in control. SUPPLY CENTER shows what it found, what supports it, and what still needs a human call.</p></div>
        <div class="feature-grid">
          <article class="feature-card feature-card-large"><div class="feature-number">01</div><div><p class="card-label">BUILD THE GRAPH</p><h3>Bring your documents.<br />Leave with structure.</h3><p>Upload facility registers, bills of material, and identity notices. SUPPLY CENTER proposes entities and relationships without hiding the raw source.</p><button class="inline-link" data-action="workspace">Open a center <span>→</span></button></div><div class="mini-graph"><span class="node node-a">Facility</span><span class="connector connector-one"></span><span class="node node-b">Component</span><span class="connector connector-two"></span><span class="node node-c">Product</span></div></article>
          <article class="feature-card"><div class="feature-number">02</div><p class="card-label">REVIEW TOGETHER</p><h3>Approve facts<br />as a table.</h3><p>Review extraction proposals in one calm queue. Approve, hold, or inspect the source behind any row.</p><div class="table-preview"><span><b class="status-dot"></b> 09 validated</span><span><b class="status-dot warn"></b> 01 needs review</span><span class="preview-arrow">→</span></div></article>
          <article class="feature-card"><div class="feature-number">03</div><p class="card-label">INVESTIGATE IMPACT</p><h3>Ask a question.<br />Trace the path.</h3><p>Choose a facility scenario and see every documented product path — then open the exact evidence in context.</p><div class="path-preview"><span class="path-node">Northbridge</span><span class="path-arrow">→</span><span class="path-node">C-17</span><span class="path-arrow">→</span><span class="path-node active">AquaPump</span></div></article>
        </div>
      </section>

      <section class="evidence-section" id="evidence"><div class="evidence-copy"><p class="eyebrow">No black boxes</p><h2>Every relationship<br /><span>has a receipt.</span></h2><p>When the graph says Northbridge affects AquaPump 500, you can open the source chunks that make that statement true. Confidence comes from being able to check.</p><button class="secondary-cta" data-action="workspace">Explore a sample center <span>↗</span></button></div><div class="evidence-card"><div class="evidence-card-top"><span class="source-type">SOURCE EVIDENCE</span><span class="source-id">facility_001</span></div><blockquote>“Northbridge Fabrication Facility manufactures Control Unit C-17.”</blockquote><div class="evidence-meta"><span>facility_register.md</span><span>chunk facility_001</span></div><div class="evidence-highlight"><span>supports</span><b>Northbridge → Control Unit C-17</b></div></div></section>

      <footer class="site-footer"><div class="brand-copy"><strong>SUPPLY CENTER</strong><small>powered by PRECISO</small></div><p>Supply chain intelligence you can stand behind.</p><span>© 2026 SUPPLY CENTER</span></footer>
    </main>
  `
}

function renderWorkspace() {
  const selectedPath = fixtures.paths[state.selectedPath]
  const approvedCount = state.approvals.size
  const sourceEvidence = fixtures.evidence[state.selectedSource]
  return `
    <main class="workspace-shell">
      <header class="workspace-topbar glass-panel"><button class="brand workspace-brand" data-action="home"><img class="workspace-brand-logo" src="${productMark}" alt="" width="36" height="36" /><span class="brand-copy"><strong>SUPPLY CENTER</strong><small>powered by PRECISO</small></span></button><div class="workspace-breadcrumb"><span>Centers</span><span>/</span><strong>Northbridge resilience review</strong></div><div class="workspace-top-actions"><span class="live-badge ${state.backendMode === 'live' ? 'is-live' : ''}"><span class="pulse"></span> ${state.backendMode === 'live' ? 'PRECISO live data' : state.backendMode === 'connected' ? 'PRECISO connected · preview data' : state.backendMode === 'checking' ? 'Checking PRECISO…' : 'Fixture preview'}</span>${state.inspectorOpen ? '' : '<button class="small-cta" data-action="open-inspector">Evidence</button>'}<button class="avatar-button" aria-label="Account menu">SE</button></div></header>
      <div class="workspace-layout ${state.inspectorOpen ? '' : 'no-inspector'}">
        <aside class="workspace-sidebar">
          <div class="sidebar-section"><div class="sidebar-heading"><span>WORKSPACE</span><button class="sidebar-add" title="New center">＋</button></div><button class="sidebar-item selected">${icon('◈')}<span>Northbridge review</span><span class="item-menu">•••</span></button><button class="sidebar-item">${icon('＋')}<span>New center</span></button></div>
          <div class="sidebar-section"><div class="sidebar-heading"><span>SOURCES <b>3</b></span><button class="sidebar-add" title="Add source">＋</button></div>${fixtures.documents.map((doc) => `<button class="sidebar-item source-item ${state.selectedSource === doc.name ? 'selected-source' : ''}" data-source="${doc.name}"><span class="file-chip">MD</span><span><b>${doc.name}</b><small>${doc.meta}</small></span></button>`).join('')}</div>
          <div class="sidebar-section sidebar-footer"><button class="sidebar-item">${icon('i')}<span>Workspace guide</span></button><button class="sidebar-item">${icon('⚙')}<span>Settings</span></button></div>
        </aside>

        <section class="chat-column">
          <div class="chat-scroll"><div class="conversation-intro"><div class="saturn-avatar"><img src="${productMark}" alt="" /></div><div><p class="eyebrow">SUPPLY CENTER ANALYST</p><h1>Northbridge resilience review</h1><p>Ask about documented dependencies, review extracted facts, or run a facility scenario. This workspace is fixture-backed for now.</p></div></div>
            <div class="user-message"><span>You</span><p>What products are exposed if Northbridge Fabrication Facility becomes unavailable?</p></div>
            <div class="assistant-message"><div class="assistant-label"><span class="mini-avatar"><img src="${productMark}" alt="" /></span><span>SUPPLY CENTER</span><span class="response-time">just now</span></div><p>Northbridge has a documented path to <strong>2 products</strong> through Control Unit C-17. AquaPump 300 and AquaPump 500 are both potentially exposed in this snapshot.</p><div class="answer-callout"><div><span class="callout-label">DOCUMENTED EXPOSURE</span><strong>2 products · 2 paths</strong></div><button class="small-cta" data-scroll="paths">Explore paths <span>→</span></button></div></div>
            ${state.messages.map((message) => `<div class="user-message"><span>You</span><p>${escapeHTML(message)}</p></div><div class="assistant-message"><div class="assistant-label"><span class="mini-avatar"><img src="${productMark}" alt="" /></span><span>SUPPLY CENTER</span><span class="response-time">just now</span></div><p>${getResponse(message)}</p></div>`).join('')}
            <div class="approval-block" id="approval"><div class="block-heading"><div><p class="eyebrow">REVIEW QUEUE</p><h2>Proposed relationships</h2></div><span class="approval-count">${approvedCount}/${fixtures.approvals.length} approved</span></div><p class="block-description">Every row is a candidate fact extracted from your source set. Select a row to inspect its evidence.</p><div class="approval-table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select all relationships" data-select-all ${approvedCount === fixtures.approvals.length ? 'checked' : ''} /></th><th>PROPOSED FACT</th><th>TYPE</th><th>SOURCE</th><th>STATUS</th></tr></thead><tbody>${fixtures.approvals.map((fact) => `<tr data-fact="${fact.id}" class="${state.approvals.has(fact.id) ? 'is-approved' : ''}"><td><input type="checkbox" aria-label="Approve ${fact.fact}" data-approval="${fact.id}" ${state.approvals.has(fact.id) ? 'checked' : ''} /></td><td><b>${fact.fact}</b></td><td><span class="type-pill">${fact.type}</span></td><td><button class="source-link" data-source="${fact.source === 'facility_001' ? 'facility_register.md' : 'product_bom.md'}">${fact.source}</button></td><td><span class="validation-pill"><span></span>${fact.status}</span></td></tr>`).join('')}</tbody></table></div></div>
            <div class="paths-block" id="paths"><div class="block-heading"><div><p class="eyebrow">SCENARIO RESULT</p><h2>If Northbridge is unavailable</h2></div><span class="result-pill">2 documented paths</span></div><div class="path-list">${fixtures.paths.map((path, index) => `<button class="path-row ${state.selectedPath === index ? 'selected-path' : ''}" data-path="${index}"><span class="path-index">0${index + 1}</span><span class="path-chain"><b>Northbridge</b><span>→</span><b>${path.component}</b><span>→</span><b>${path.product}</b></span><span class="path-confidence ${path.tone}">${path.confidence}</span></button>`).join('')}</div></div>
          </div>
          <form class="composer" id="composer"><button type="button" class="composer-plus" title="Attach documents">＋</button><input name="message" autocomplete="off" placeholder="Ask about your dependencies…" aria-label="Ask SUPPLY CENTER" /><button class="composer-send" type="submit" aria-label="Send message">↑</button><div class="composer-hint">Fixture mode · Enter to send</div></form>
        </section>

        ${state.inspectorOpen ? `<aside class="evidence-panel"><div class="panel-heading"><div><p class="eyebrow">INSPECTOR</p><h2>Evidence</h2></div><button class="panel-close" data-action="close-inspector" title="Close inspector">×</button></div><div class="inspector-tabs"><span class="active">Evidence</span></div><div class="selected-source-card"><div class="selected-source-header"><span class="file-chip">MD</span><div><b>${state.selectedSource}</b><small>Source document</small></div><span class="verified-tag">verified</span></div><div class="source-preview"><div class="line-number">${sourceEvidence.chunk}</div><p><mark>${sourceEvidence.primary}</mark></p><div class="line-number">context</div><p class="muted-line">${sourceEvidence.secondary}</p></div><div class="source-footer"><span>${sourceEvidence.chunk}</span><span class="source-type">resolved chunk</span></div></div><div class="evidence-detail"><p class="eyebrow">SELECTED PATH</p><div class="detail-chain"><b>Northbridge</b><span>→</span><b>${selectedPath.component}</b><span>→</span><b>${selectedPath.product}</b></div><p class="detail-copy">This path uses two direct documented edges and matches the current snapshot date.</p><div class="detail-row"><span>Snapshot</span><b>2026-01-15</b></div><div class="detail-row"><span>Evidence basis</span><b class="blue-text">Direct statements</b></div></div><div class="panel-note"><span class="pulse"></span><p>Answers are limited to accepted relationships and their source evidence.</p></div></aside>` : ''}
      </div>
    </main>
  `
}

function getResponse(message) {
  const normalized = message.toLowerCase()
  if (normalized.includes('facility') || normalized.includes('northbridge')) return 'Northbridge Fabrication Facility is documented as manufacturing Control Unit C-17. That component is used in AquaPump 300 and AquaPump 500. I found no documented impact to ValvePro 10.'
  if (normalized.includes('source') || normalized.includes('evidence')) return 'The strongest evidence is facility_001 in facility_register.md, paired with bom_001 in product_bom.md. Select any row to inspect the source text.'
  return 'I can trace that against the accepted fixture relationships. Try asking about a facility, a product, or the evidence behind a path.'
}

async function checkBackend() {
  try {
    const response = await fetch('/api/status', { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`status ${response.status}`)
    const status = await response.json()
    if (status.status === 'error') throw new Error('backend reported an error')
    state.backendMode = 'connected'
    const query = await fetch('/api/investigate?facility_id=facility%3Aarkon-components%3Anorthbridge&max_paths=100')
    if (query.ok && (await query.json()).status === 'success') state.backendMode = 'live'
  } catch {
    state.backendMode = 'fixture'
  }
  if (state.screen === 'workspace') render()
}

function bindEvents() {
  document.querySelectorAll('[data-action="workspace"]').forEach((button) => button.addEventListener('click', () => { state.screen = 'workspace'; render(); window.scrollTo(0, 0) }))
  document.querySelectorAll('[data-action="home"]').forEach((button) => button.addEventListener('click', () => { state.screen = 'home'; render(); window.scrollTo(0, 0) }))
  document.querySelectorAll('[data-action="close-inspector"]').forEach((button) => button.addEventListener('click', () => { state.inspectorOpen = false; render() }))
  document.querySelectorAll('[data-action="open-inspector"]').forEach((button) => button.addEventListener('click', () => { state.inspectorOpen = true; render() }))
  document.querySelectorAll('[data-source]').forEach((button) => button.addEventListener('click', () => { state.selectedSource = button.dataset.source; render() }))
  document.querySelectorAll('[data-path]').forEach((button) => button.addEventListener('click', () => { state.selectedPath = Number(button.dataset.path); render() }))
  document.querySelectorAll('[data-approval]').forEach((checkbox) => checkbox.addEventListener('change', (event) => { const id = Number(event.target.dataset.approval); event.target.checked ? state.approvals.add(id) : state.approvals.delete(id); render() }))
  const selectAll = document.querySelector('[data-select-all]')
  if (selectAll) selectAll.addEventListener('change', (event) => { state.approvals = event.target.checked ? new Set(fixtures.approvals.map((fact) => fact.id)) : new Set(); render() })
  document.querySelectorAll('[data-scroll]').forEach((button) => button.addEventListener('click', () => document.querySelector(`#${button.dataset.scroll}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })))
  const composer = document.querySelector('#composer')
  if (composer) composer.addEventListener('submit', (event) => { event.preventDefault(); const input = composer.elements.message; if (!input.value.trim()) return; state.messages.push(input.value.trim()); input.value = ''; render(); requestAnimationFrame(() => document.querySelector('.chat-scroll')?.scrollTo({ top: document.querySelector('.chat-scroll').scrollHeight, behavior: 'smooth' })) })
}

render()
checkBackend()
