'use strict';

// ── State ─────────────────────────────────────────────
let allResults    = [];
let aiAbortCtrl   = null;
let activeFilter  = null;
let isGridView    = true;
let productModal  = null;
let compareModal  = null;
let currentSort   = 'relevance';
let compareSet    = new Set();   // product_ids selected for compare
let lastQueryType = '';
let lastQuery     = '';

// ── DOM helpers ───────────────────────────────────────
function el(id)          { return document.getElementById(id); }
function show(id)        { const e = el(id); if (e) e.style.removeProperty('display'); }
function hide(id)        { const e = el(id); if (e) e.style.display = 'none'; }
function setText(id, v)  { const e = el(id); if (e) e.textContent = v; }
function setHTML(id, v)  { const e = el(id); if (e) e.innerHTML = v; }

// ── Bootstrap modals ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const mEl = el('productModal');
  const cEl = el('compareModal');
  if (mEl) productModal = new bootstrap.Modal(mEl);
  if (cEl) compareModal  = new bootstrap.Modal(cEl);
});

// ── Dark mode ─────────────────────────────────────────
const themeToggle = el('themeToggle');
if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const html   = document.documentElement;
    const isDark = html.getAttribute('data-bs-theme') === 'dark';
    html.setAttribute('data-bs-theme', isDark ? 'light' : 'dark');
    themeToggle.innerHTML = isDark
      ? '<i class="bi bi-moon-fill"></i>'
      : '<i class="bi bi-sun-fill"></i>';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
  });
  // Restore saved theme
  const saved = localStorage.getItem('theme');
  if (saved) {
    document.documentElement.setAttribute('data-bs-theme', saved);
    themeToggle.innerHTML = saved === 'dark'
      ? '<i class="bi bi-sun-fill"></i>'
      : '<i class="bi bi-moon-fill"></i>';
  }
}

// ── Shareable URL — read ?q= on load ──────────────────
window.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const q = params.get('q');
  if (q) {
    const inp = el('searchInput');
    if (inp) { inp.value = q; runSearch(); }
  }
});

function pushSearchUrl(query) {
  const url = new URL(window.location.href);
  url.searchParams.set('q', query);
  history.pushState({}, '', url.toString());
}

// ── Suggestion chips ──────────────────────────────────
function setQuery(q) {
  const inp = el('searchInput');
  if (inp) { inp.value = q; runSearch(); }
}

// ── View toggle ───────────────────────────────────────
const viewGrid = el('viewGrid');
const viewList = el('viewList');
if (viewGrid) viewGrid.addEventListener('click', () => {
  isGridView = true;
  viewGrid.classList.add('active');
  if (viewList) viewList.classList.remove('active');
  render(filteredSortedResults());
});
if (viewList) viewList.addEventListener('click', () => {
  isGridView = false;
  viewList.classList.add('active');
  if (viewGrid) viewGrid.classList.remove('active');
  render(filteredSortedResults());
});

// ── Sort ──────────────────────────────────────────────
function setSort(btn, sortKey) {
  currentSort = sortKey;
  document.querySelectorAll('#sortBtns .btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render(filteredSortedResults());
}

function sortResults(results) {
  const arr = [...results];
  switch (currentSort) {
    case 'price_asc':  return arr.sort((a,b) => a.price - b.price);
    case 'price_desc': return arr.sort((a,b) => b.price - a.price);
    case 'warranty':   return arr.sort((a,b) => b.warranty - a.warranty);
    case 'energy':     return arr.sort((a,b) => energyStars(b.energy_rating) - energyStars(a.energy_rating));
    default:           return arr; // relevance — original order
  }
}

function energyStars(rating) {
  if (!rating) return 0;
  const m = rating.match(/(\d)/);
  return m ? parseInt(m[1]) : 0;
}

// ── Advanced filters ──────────────────────────────────
function applyAdvFilters() { render(filteredSortedResults()); }

function advFilterResults(results) {
  let out = [...results];
  // Stock filter
  const inStockOnly = el('fStock-in') && el('fStock-in').checked;
  if (inStockOnly) out = out.filter(r => (r.stock_status||'').toLowerCase().includes('in stock'));
  // Warranty filter
  const minWarranty = parseInt(el('fWarranty')?.value || '0');
  if (minWarranty > 0) out = out.filter(r => (r.warranty||0) >= minWarranty);
  // Energy filter
  const minEnergy = parseInt(el('fEnergy')?.value || '0');
  if (minEnergy > 0) out = out.filter(r => energyStars(r.energy_rating) >= minEnergy);
  return out;
}

// ── Combined filter + sort pipeline ───────────────────
function filteredSortedResults() {
  let r = activeFilter ? allResults.filter(r => r.category === activeFilter) : allResults;
  r = advFilterResults(r);
  return sortResults(r);
}

// ── Pipeline steps ────────────────────────────────────
const STEPS = ['ps-preprocess','ps-keyword','ps-embed','ps-faiss','ps-rank','ps-groq'];

function resetPipeline() {
  STEPS.forEach(id => {
    const e = el(id);
    if (e) e.classList.remove('active','done');
  });
}

async function animatePipelineSteps(count) {
  const wrap = el('pipelineWrap');
  if (wrap) wrap.style.display = 'block';
  for (let i = 0; i < Math.min(count, STEPS.length); i++) {
    const e = el(STEPS[i]);
    if (!e) continue;
    e.classList.add('active');
    await sleep(220);
    e.classList.remove('active');
    e.classList.add('done');
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Search ────────────────────────────────────────────
const searchBtn   = el('searchBtn');
const searchInput = el('searchInput');
if (searchBtn)   searchBtn.addEventListener('click', runSearch);
if (searchInput) searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') runSearch();
});

async function runSearch() {
  const inp   = el('searchInput');
  const query = inp ? inp.value.trim() : '';
  if (!query) return;

  lastQuery = query;
  activeFilter  = null;
  currentSort   = 'relevance';
  compareSet.clear();
  updateCompareBtn();

  resetAll();
  setSearchLoading(true);
  resetPipeline();
  pushSearchUrl(query);

  // Reset sort buttons to default
  document.querySelectorAll('#sortBtns .btn').forEach(b => {
    b.classList.toggle('active', b.dataset.sort === 'relevance');
  });

  try {
    const res = await fetch('/api/search', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query }),
    });

    let data;
    try { data = await res.json(); }
    catch (_) {
      showError(`Server returned non-JSON response (status ${res.status}).`);
      return;
    }

    if (!res.ok) {
      const msg    = data.error  || 'Search failed';
      const detail = data.detail || '';
      const lines  = detail ? detail.split('\n').filter(Boolean).slice(-4).join('\n') : '';
      showError(`${msg}${lines ? '\n\n' + lines : ''}`);
      return;
    }

    // Spell correction notice
    const fixes = data.spell_correction || [];
    if (fixes.length > 0) {
      el('spellNoticeText').textContent =
        `Corrected: ${fixes.join(', ')} → searching for "${data.query}"`;
      el('spellNotice').classList.remove('d-none');
    } else {
      el('spellNotice').classList.add('d-none');
    }

    // Cache hit notice
    if (data.from_cache) {
      el('cacheNotice').classList.remove('d-none');
    } else {
      el('cacheNotice').classList.add('d-none');
    }

    const stepCount = ['greeting','off_topic','unclear'].includes(data.query_type) ? 2 : 5;
    animatePipelineSteps(stepCount);

    allResults    = data.results || [];
    lastQueryType = data.query_type;
    setSearchLoading(false);

    if (data.message) {
      showMessageBanner(data.message, data.query_type);
      return;
    }

    hideBanner();
    updateStats(data);
    updateFilters();
    show('advFilterCard');
    show('sortCard');
    render(filteredSortedResults());

    if (allResults.length > 0) {
      const label = data.query_type === 'product_id' ? '📋 Product Summary' : '✨ AI Recommendation';
      streamAIAnswer(data.query, data.query_type, allResults, label);
    }

  } catch (err) {
    setSearchLoading(false);
    showError(`Request failed: ${err.message || err}`);
    console.error('[runSearch error]', err);
  }
}

// ── Stream AI answer ──────────────────────────────────
async function streamAIAnswer(query, queryType, results, label) {
  const aiAnswer  = el('aiAnswer');
  const aiSpin    = el('aiAnswerSpinner');
  const aiText    = el('aiAnswerText');
  if (!aiAnswer) return;

  if (aiAbortCtrl) { aiAbortCtrl.abort(); aiAbortCtrl = null; }
  aiAbortCtrl = new AbortController();
  const signal = aiAbortCtrl.signal;

  setText('aiAnswerLabel', label || '✨ AI Recommendation');
  setText('aiAnswerText', '');
  if (aiSpin) aiSpin.style.display = 'inline-block';
  aiAnswer.style.removeProperty('display');

  const groqEl = el('ps-groq');
  if (groqEl) groqEl.classList.add('active');

  try {
    const res = await fetch('/api/ai-answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, query_type: queryType, results }),
      signal,
    });

    if (!res.ok || !res.body) {
      if (aiSpin) aiSpin.style.display = 'none';
      if (groqEl) { groqEl.classList.remove('active'); groqEl.classList.add('done'); }
      return;
    }

    await readStream(res.body, chunk => {
      if (aiSpin) aiSpin.style.display = 'none';
      if (aiText) aiText.textContent += chunk;
    });

  } catch (e) {
    if (e.name === 'AbortError') return;
    console.warn('[streamAIAnswer]', e);
  } finally {
    if (aiSpin) aiSpin.style.display = 'none';
    if (groqEl) { groqEl.classList.remove('active'); groqEl.classList.add('done'); }
    const txt = el('aiAnswerText');
    if (txt && !txt.textContent.trim() && aiAnswer) aiAnswer.style.display = 'none';
  }
}

// ── Compare logic ─────────────────────────────────────
function toggleCompare(productId) {
  if (compareSet.has(productId)) {
    compareSet.delete(productId);
  } else {
    if (compareSet.size >= 3) {
      alert('You can compare up to 3 products. Deselect one first.');
      return;
    }
    compareSet.add(productId);
  }
  updateCompareBtn();
  render(filteredSortedResults()); // re-render to update checkbox states
}

function updateCompareBtn() {
  const btn = el('compareBtn');
  const cnt = el('compareCount');
  if (!btn) return;
  if (compareSet.size >= 2) {
    btn.classList.remove('d-none');
    if (cnt) cnt.textContent = compareSet.size;
  } else {
    btn.classList.add('d-none');
  }
}

async function openCompareModal() {
  const selected = allResults.filter(r => compareSet.has(r.product_id));
  if (selected.length < 2) return;

  const body = el('compareModalBody');
  if (!body) return;

  // Build comparison table
  const fields = [
    ['Brand',    r => r.brand],
    ['Category', r => r.category],
    ['Model',    r => r.model],
    ['Capacity', r => r.capacity],
    ['Price',    r => `PKR ${(r.price||0).toLocaleString()}`],
    ['Energy',   r => r.energy_rating],
    ['Warranty', r => `${r.warranty} yr`],
    ['Stock',    r => `<span class="badge border ${stockBadgeClass(r.stock_status)}">${r.stock_status}</span>`],
    ['Score',    r => `${((r.combined_score||0)*100).toFixed(1)}%`],
  ];

  const colW = Math.floor(12 / (selected.length + 1));
  let table = `<table class="table table-bordered table-sm small align-middle">
    <thead class="table-light">
      <tr>
        <th style="width:130px">Feature</th>
        ${selected.map(r => `<th class="text-center">${r.brand}<br><span class="text-body-secondary fw-normal">${r.name}</span></th>`).join('')}
      </tr>
    </thead>
    <tbody>`;

  for (const [label, getter] of fields) {
    table += `<tr><td class="fw-semibold text-body-secondary">${label}</td>`;
    for (const r of selected) {
      table += `<td class="text-center">${getter(r)}</td>`;
    }
    table += '</tr>';
  }
  table += '</tbody></table>';

  body.innerHTML = `
    <div class="table-responsive mb-4">${table}</div>
    <div id="compareAnswerModal" class="alert alert-warning d-flex gap-3 align-items-start" style="display:none!important">
      <i class="bi bi-stars fs-5 flex-shrink-0 mt-1"></i>
      <div class="w-100">
        <div class="d-flex align-items-center gap-2 mb-1">
          <span class="fw-semibold small">⚖️ AI Verdict</span>
          <span id="compareSpinModal" class="spinner-border spinner-border-sm text-warning" role="status"></span>
        </div>
        <div id="compareTextModal" class="small"></div>
      </div>
    </div>`;

  if (compareModal) compareModal.show();

  // Stream compare AI
  const answerEl = body.querySelector('#compareAnswerModal');
  const spinEl   = body.querySelector('#compareSpinModal');
  const textEl   = body.querySelector('#compareTextModal');
  if (answerEl) answerEl.style.removeProperty('display');

  try {
    const res = await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ products: selected, query: lastQuery }),
    });
    if (!res.ok || !res.body) { if (spinEl) spinEl.style.display='none'; return; }

    await readStream(res.body, chunk => {
      if (spinEl) spinEl.style.display = 'none';
      if (textEl) textEl.textContent += chunk;
    });
  } catch(e) {
    console.warn('[compare stream]', e);
  } finally {
    if (spinEl) spinEl.style.display = 'none';
  }
}

function clearCompare() {
  compareSet.clear();
  updateCompareBtn();
  if (compareModal) compareModal.hide();
  render(filteredSortedResults());
}

// Wire up compare button
const compareBtn = el('compareBtn');
if (compareBtn) compareBtn.addEventListener('click', openCompareModal);

// ── Generic SSE stream reader ─────────────────────────
async function readStream(body, onChunk) {
  const reader  = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6).trim();
      if (payload === '[DONE]') return;
      try { const obj = JSON.parse(payload); if (obj.chunk) onChunk(obj.chunk); } catch(_) {}
    }
  }
}

// ── Stats ─────────────────────────────────────────────
function updateStats(data) {
  setText('statResults', data.result_count ?? '—');
  setText('statTime',    data.elapsed_ms   ?? '—');
  setText('statKw',      data.keyword_hits  ?? '—');
  setText('statVec',     data.vector_hits   ?? '—');
  show('statsCard');
}

// ── Category filters ──────────────────────────────────
function updateFilters() {
  const cats = [...new Set(allResults.map(r => r.category))].sort();
  const fc   = el('categoryFilters');
  if (!fc) return;
  if (cats.length <= 1) { hide('filterCard'); return; }
  fc.innerHTML = '';
  fc.appendChild(makeFilterBtn('All', null));
  cats.forEach(cat => fc.appendChild(makeFilterBtn(cat, cat)));
  show('filterCard');
}

function makeFilterBtn(label, value) {
  const btn = document.createElement('button');
  btn.className = 'btn btn-sm text-start ' +
    (activeFilter === value ? 'btn-primary' : 'btn-outline-secondary');
  btn.textContent = label;
  btn.addEventListener('click', () => {
    activeFilter = value;
    updateFilters();
    render(filteredSortedResults());
  });
  return btn;
}

// ── Message banner ────────────────────────────────────
function showMessageBanner(message, queryType) {
  const banner = el('messageBanner');
  const text   = el('messageBannerText');
  if (!banner || !text) return;
  const cls = {
    greeting:  'alert-info',
    off_topic: 'alert-warning',
    unclear:   'alert-secondary',
  }[queryType] || 'alert-secondary';
  banner.className = `alert ${cls} d-flex gap-2 align-items-start`;
  text.innerHTML   = message.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  banner.style.removeProperty('display');
  setSearchLoading(false);
}
function hideBanner() { hide('messageBanner'); }

// ── Render product cards ──────────────────────────────
// Category icon map
const CAT_ICON = {
  'Air Conditioner': '<i class="bi bi-wind"></i>',
  'Refrigerator':    '<i class="bi bi-snow"></i>',
  'Washing Machine': '<i class="bi bi-moisture"></i>',
  'Microwave Oven':  '<i class="bi bi-broadcast"></i>',
  'Water Dispenser': '<i class="bi bi-droplet-fill"></i>',
};

function render(results) {
  const grid   = el('resultsGrid');
  const header = el('resultsHeader');
  const label  = el('resultsLabel');
  if (!grid) return;

  grid.innerHTML = '';

  if (!results.length) {
    if (header) header.style.display = 'none';
    return;
  }

  if (header) header.style.removeProperty('display');
  if (label)  label.textContent = `${results.length} result${results.length !== 1 ? 's' : ''}`;

  const maxScore = results[0]?.combined_score || 1;

  results.forEach((r, idx) => {
    const colDiv     = document.createElement('div');
    colDiv.className = isGridView ? 'col-sm-6 col-xl-4' : 'col-12';

    const score      = r.combined_score || 0;
    const pct        = Math.round((score / maxScore) * 100);
    const scoreColor = score > 0.6 ? '#198754' : score > 0.3 ? '#0d6efd' : '#6c757d';
    const stockClass = stockBadgeClass(r.stock_status);
    const catIcon    = CAT_ICON[r.category] || '🔌';
    const isSelected = compareSet.has(r.product_id);

    colDiv.innerHTML = `
      <div class="product-card p-3 card-anim ${isSelected ? 'compare-selected' : ''}"
           style="animation-delay:${idx * 0.04}s">

        <!-- Compare checkbox -->
        <div class="d-flex justify-content-between align-items-start mb-2">
          <div class="d-flex align-items-start gap-2 flex-grow-1" onclick="openModal(${idx})" style="cursor:pointer">
            <span class="cat-icon">${catIcon}</span>
            <div>
              <div class="fw-semibold" style="font-size:14px">${r.brand} ${r.name}</div>
              <div class="text-body-secondary" style="font-size:12px">
                ${r.category} ·
                <span class="fw-semibold text-warning-emphasis">${r.product_id}</span>
              </div>
            </div>
          </div>
          <div class="d-flex flex-column align-items-end gap-1 ms-2 flex-shrink-0">
            <div class="text-end">
              <div class="fw-semibold" style="font-size:12px;color:${scoreColor}">${(score*100).toFixed(1)}%</div>
              <div class="score-bar-bg mt-1" style="width:72px">
                <div class="score-bar-fill" style="width:${pct}%;background:${scoreColor}"></div>
              </div>
            </div>
            <input type="checkbox" class="form-check-input compare-check mt-1"
              title="Add to compare"
              ${isSelected ? 'checked' : ''}
              onclick="event.stopPropagation(); toggleCompare('${r.product_id}')">
          </div>
        </div>

        <div class="text-body-secondary mb-2" style="font-size:12px;line-height:1.5;cursor:pointer"
             onclick="openModal(${idx})">
          ${(r.features || r.description || '').slice(0,100)}…
        </div>

        <div class="d-flex justify-content-between align-items-center flex-wrap gap-1 mb-2"
             onclick="openModal(${idx})" style="cursor:pointer">
          <div>
            <span class="fw-semibold text-primary" style="font-size:13px">
              PKR ${(r.price||0).toLocaleString()}
            </span>
            <span class="text-body-tertiary ms-1" style="font-size:11px">
              · ${r.energy_rating} · ${r.warranty}yr
            </span>
          </div>
          <span class="badge border ${stockClass}" style="font-size:10px">${r.stock_status}</span>
        </div>
        <div class="d-flex gap-2 flex-wrap mt-1 align-items-center">
          ${buildShopButtons(r.shop_links, true)}
        </div>
      </div>`;

    grid.appendChild(colDiv);
  });
}

// ── Product detail modal ──────────────────────────────
function openModal(idx) {
  const r = filteredSortedResults()[idx];
  if (!r) return;

  setText('productModalLabel', `${r.brand} ${r.name}`);
  setHTML('productModalBody', `
    <div class="row g-3">
      <div class="col-md-6">
        <table class="table table-sm table-borderless small">
          <tr><th class="text-body-secondary fw-normal" style="width:42%">Product ID</th>
              <td class="fw-semibold">${r.product_id}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Brand</th><td>${r.brand}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Model</th><td>${r.model}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Category</th><td>${r.category}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Capacity</th><td>${r.capacity}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Color</th><td>${r.color}</td></tr>
          <tr><th class="text-body-secondary fw-normal">Energy</th>
              <td><span class="badge text-bg-success">${r.energy_rating}</span></td></tr>
          <tr><th class="text-body-secondary fw-normal">Warranty</th><td>${r.warranty} yr</td></tr>
          <tr><th class="text-body-secondary fw-normal">Stock</th>
              <td><span class="badge border ${stockBadgeClass(r.stock_status)}">${r.stock_status}</span></td></tr>
        </table>
      </div>
      <div class="col-md-6">
        <div class="mb-3">
          <div class="text-body-secondary small mb-1">Price</div>
          <div class="fs-4 fw-semibold text-primary">PKR ${(r.price||0).toLocaleString()}</div>
        </div>
        <div class="mb-3">
          <div class="text-body-secondary small mb-1">Key Features</div>
          <div class="small">${r.features || '—'}</div>
        </div>
        <div>
          <div class="text-body-secondary small mb-1">Description</div>
          <div class="small text-body-secondary">${r.description || '—'}</div>
        </div>
      </div>
      <div class="col-12">
        <hr class="my-2"/>
        <div class="mb-2 fw-semibold small text-body-secondary text-uppercase" style="font-size:11px;letter-spacing:.4px">
          <i class="bi bi-bag-check me-1"></i>Buy This Product
        </div>
        <div class="d-flex gap-2 flex-wrap">
          ${buildShopButtons(r.shop_links, false)}
        </div>
      </div>
      <div class="col-12">
        <hr class="my-1"/>
        <div class="d-flex gap-3 small text-body-secondary">
          <span>Retriever: ${((r.retriever_score||0)*100).toFixed(1)}%</span>
          <span>FAISS: ${((r.faiss_score||0)*100).toFixed(1)}%</span>
          <span>Combined: ${((r.combined_score||0)*100).toFixed(1)}%</span>
        </div>
      </div>
    </div>`);

  if (productModal) productModal.show();
}

// ── Helpers ───────────────────────────────────────────
function stockBadgeClass(s) {
  if (!s) return 'stock-out';
  const v = s.toLowerCase();
  if (v.includes('in stock')) return 'stock-in';
  if (v.includes('limited'))  return 'stock-low';
  return 'stock-out';
}

function setSearchLoading(on) {
  hide('skeletonGrid');
  const spin  = el('spinner');
  const empty = el('emptyState');
  const skel  = el('skeletonGrid');
  const btn   = el('searchBtn');

  if (on) {
    if (skel) skel.style.removeProperty('display');
    if (spin) spin.style.display = 'none';
  } else {
    if (skel) skel.style.display = 'none';
    if (spin) spin.style.display = 'none';
  }

  if (empty) empty.style.display = on ? 'none' : (allResults.length ? 'none' : 'block');
  if (btn)   btn.disabled = on;
}

function resetAll() {
  if (aiAbortCtrl) { aiAbortCtrl.abort(); aiAbortCtrl = null; }

  const grid = el('resultsGrid');
  if (grid) grid.innerHTML = '';

  setText('aiAnswerText', '');
  const aiSpin = el('aiAnswerSpinner');
  if (aiSpin) aiSpin.style.display = 'none';

  hide('resultsHeader');
  hide('aiAnswer');
  hide('compareAnswer');
  hide('advFilterCard');
  hide('sortCard');

  const bannerText = el('messageBannerText');
  if (bannerText) bannerText.innerHTML = '';
  hide('messageBanner');
  hide('statsCard');
  hide('filterCard');
  el('spellNotice')?.classList.add('d-none');
  el('cacheNotice')?.classList.add('d-none');

  allResults = [];
}

function showError(msg) {
  setSearchLoading(false);
  const safe = msg.replace(/\n/g, '<br>');
  setHTML('resultsGrid', `
    <div class="col-12">
      <div class="alert alert-danger">
        <i class="bi bi-exclamation-circle-fill me-2"></i>
        <strong>Error:</strong> ${safe}
      </div>
    </div>`);
}

/* ═══════════════════════════════════════════════════════
   PROFESSIONAL SEARCH BAR FEATURES
   ═══════════════════════════════════════════════════════ */

// ── Autocomplete vocabulary ───────────────────────────
const AC_SUGGESTIONS = [
  'Haier inverter AC 1.5 ton','Haier AC 1 ton','Gree inverter AC',
  'Kenwood DC inverter AC','Dawlance split AC','Orient AC 1.5 ton',
  'Haier no frost refrigerator','Dawlance fridge large capacity',
  'PEL refrigerator','Samsung refrigerator inverter',
  'Haier fully automatic washing machine','Dawlance washing machine',
  'Samsung front load washing machine','LG washing machine 8kg',
  'Haier microwave oven','Dawlance microwave grill',
  'Kenwood microwave digital','Orient microwave',
  'Haier water dispenser hot cold','Dawlance dispenser',
  'Waves water dispenser','energy efficient AC',
  'cheap fridge under 50000','best washing machine',
  'inverter refrigerator','no frost fridge large',
  'AC under 50000','fridge between 50000 and 100000',
  'washing machine above 100000','budget microwave',
];

// ── Placeholder cycling ───────────────────────────────
const PLACEHOLDERS = [
  'Search "Haier inverter AC 1.5 ton"…',
  'Try "energy efficient fridge under 80k"…',
  'Search "Samsung front load washing machine"…',
  'Try "Dawlance no frost large refrigerator"…',
  'Search "Kenwood microwave grill 30L"…',
  'Try "water dispenser hot and cold"…',
  'Search "best AC for large room"…',
  'Try "Gree DC inverter 2 ton"…',
];

let _phIdx   = 0;
let _phTimer = null;
let _phTyping = true;
let _phText  = '';
let _phFull  = '';
let _phCharIdx = 0;

function startPlaceholderCycle() {
  const el = document.getElementById('placeholderText');
  if (!el) return;

  function nextPhrase() {
    _phFull    = PLACEHOLDERS[_phIdx % PLACEHOLDERS.length];
    _phCharIdx = 0;
    _phTyping  = true;
    typeChar();
  }

  function typeChar() {
    const inp = document.getElementById('searchInput');
    // pause if user is typing
    if (inp && inp.value.trim()) { _phTimer = setTimeout(typeChar, 200); return; }
    if (_phTyping) {
      if (_phCharIdx <= _phFull.length) {
        el.textContent = _phFull.slice(0, _phCharIdx++);
        _phTimer = setTimeout(typeChar, 42);
      } else {
        _phTimer = setTimeout(() => { _phTyping = false; eraseChar(); }, 1800);
      }
    }
  }

  function eraseChar() {
    const inp = document.getElementById('searchInput');
    if (inp && inp.value.trim()) { _phTimer = setTimeout(eraseChar, 200); return; }
    if (el.textContent.length > 0) {
      el.textContent = el.textContent.slice(0, -1);
      _phTimer = setTimeout(eraseChar, 22);
    } else {
      _phIdx++;
      _phTimer = setTimeout(nextPhrase, 400);
    }
  }

  nextPhrase();
}

// Hide/show placeholder based on input value
function syncPlaceholder() {
  const inp = document.getElementById('searchInput');
  const ph  = document.getElementById('searchPlaceholder');
  if (!inp || !ph) return;
  ph.classList.toggle('hidden', inp.value.length > 0);
}

// ── Search history (localStorage) ────────────────────
const HISTORY_KEY = 'appliance_search_history';
const HISTORY_MAX = 8;

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch (_) { return []; }
}
function saveHistory(query) {
  let h = getHistory().filter(q => q.toLowerCase() !== query.toLowerCase());
  h.unshift(query);
  if (h.length > HISTORY_MAX) h = h.slice(0, HISTORY_MAX);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch(_) {}
}
function clearHistory() {
  try { localStorage.removeItem(HISTORY_KEY); } catch(_) {}
  renderDropdown('');
}

// ── Dropdown logic ────────────────────────────────────
let _dropdownOpen = false;
let _highlighted  = -1;
let _dropdownItems = [];

function openDropdown() {
  const dd  = document.getElementById('searchDropdown');
  const box = document.getElementById('searchBox');
  if (!dd || !box) return;
  dd.classList.add('open');
  box.classList.add('dropdown-open');
  _dropdownOpen = true;
}
function closeDropdown() {
  const dd  = document.getElementById('searchDropdown');
  const box = document.getElementById('searchBox');
  if (!dd || !box) return;
  dd.classList.remove('open');
  box.classList.remove('dropdown-open');
  _dropdownOpen = false;
  _highlighted  = -1;
}

function renderDropdown(query) {
  const histSec  = document.getElementById('historySection');
  const histList = document.getElementById('historyList');
  const acSec    = document.getElementById('autocompleteSection');
  const acList   = document.getElementById('autocompleteList');
  _dropdownItems = [];

  const q = query.trim().toLowerCase();

  if (q.length === 0) {
    // Show history only
    const history = getHistory();
    if (histSec)  histSec.style.display  = history.length ? '' : 'none';
    if (acSec)    acSec.style.display    = 'none';

    if (histList) {
      histList.innerHTML = '';
      history.forEach(item => {
        const row = makeDropdownItem('bi-clock-history', item, () => { setQueryDirect(item); });
        histList.appendChild(row);
        _dropdownItems.push(row);
      });
    }
  } else {
    // Show autocomplete
    if (histSec) histSec.style.display = 'none';
    const matches = AC_SUGGESTIONS
      .filter(s => s.toLowerCase().includes(q))
      .slice(0, 7);

    if (acSec)   acSec.style.display   = matches.length ? '' : 'none';
    if (acList)  {
      acList.innerHTML = '';
      matches.forEach(item => {
        const row = makeDropdownItem('bi-search', item, () => { setQueryDirect(item); });
        acList.appendChild(row);
        _dropdownItems.push(row);
      });
    }
  }

  if (_dropdownItems.length > 0) {
    openDropdown();
  } else {
    closeDropdown();
  }
}

function makeDropdownItem(icon, label, onClick) {
  const div = document.createElement('div');
  div.className = 'dropdown-item-row';
  div.innerHTML = `
    <span class="item-icon"><i class="bi ${icon}"></i></span>
    <span class="item-label">${label}</span>
    <i class="bi bi-arrow-up-left item-arrow"></i>`;
  div.addEventListener('mousedown', e => { e.preventDefault(); onClick(); });
  return div;
}

function setQueryDirect(q) {
  const inp = document.getElementById('searchInput');
  if (inp) inp.value = q;
  syncPlaceholder();
  closeDropdown();
  runSearch();
}

// Keyboard navigation in dropdown
function handleDropdownKey(e) {
  if (!_dropdownOpen) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _highlighted = Math.min(_highlighted + 1, _dropdownItems.length - 1);
    updateHighlight();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _highlighted = Math.max(_highlighted - 1, -1);
    updateHighlight();
  } else if (e.key === 'Escape') {
    closeDropdown();
  } else if (e.key === 'Enter') {
    if (_highlighted >= 0 && _dropdownItems[_highlighted]) {
      e.preventDefault();
      _dropdownItems[_highlighted].dispatchEvent(new Event('mousedown'));
    }
  }
}

function updateHighlight() {
  _dropdownItems.forEach((row, i) => {
    row.classList.toggle('highlighted', i === _highlighted);
  });
}

// ── Wire up input events ──────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById('searchInput');
  const clr = document.getElementById('clearBtn');
  if (!inp) return;

  // Typing → autocomplete
  inp.addEventListener('input', () => {
    syncPlaceholder();
    const q = inp.value.trim();
    if (clr) clr.classList.toggle('d-none', q.length === 0);
    renderDropdown(q);
    _highlighted = -1;
  });

  // Focus → show history if empty
  inp.addEventListener('focus', () => {
    renderDropdown(inp.value.trim());
  });

  // Blur → close dropdown (small delay to allow click)
  inp.addEventListener('blur', () => {
    setTimeout(closeDropdown, 160);
  });

  // Keyboard nav
  inp.addEventListener('keydown', handleDropdownKey);

  // Close dropdown on outside click
  document.addEventListener('click', e => {
    const wrap = document.getElementById('searchBox');
    if (wrap && !wrap.contains(e.target)) closeDropdown();
  });

  // Start animated placeholder
  startPlaceholderCycle();
});

// ── Clear button ──────────────────────────────────────
const _clearBtn = document.getElementById('clearBtn');
if (_clearBtn) {
  _clearBtn.addEventListener('click', () => {
    const inp = document.getElementById('searchInput');
    if (inp) { inp.value = ''; inp.focus(); }
    _clearBtn.classList.add('d-none');
    syncPlaceholder();
    closeDropdown();
    renderDropdown('');
  });
}

// ── Override setQuery to also save history ────────────
const _origSetQuery = window.setQuery;
window.setQuery = function(q) {
  const inp = document.getElementById('searchInput');
  if (inp) inp.value = q;
  syncPlaceholder();
  const clr = document.getElementById('clearBtn');
  if (clr) clr.classList.toggle('d-none', !q);
  closeDropdown();
  runSearch();
};

// ── Override runSearch to save history ────────────────
const _origRunSearch = window.runSearch;
window.runSearch = async function() {
  const inp = document.getElementById('searchInput');
  const q   = inp ? inp.value.trim() : '';
  if (q) saveHistory(q);
  closeDropdown();
  await _origRunSearch.apply(this, arguments);
};

// ── Voice input ───────────────────────────────────────
const voiceBtn  = document.getElementById('voiceBtn');
const voiceIcon = document.getElementById('voiceIcon');
const voiceRow  = document.getElementById('voiceListening');
let   _recognition = null;

if (voiceBtn) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    voiceBtn.title   = 'Voice search not supported in this browser';
    voiceBtn.disabled = true;
    voiceBtn.style.opacity = '0.35';
  } else {
    voiceBtn.addEventListener('click', () => {
      if (_recognition) {
        _recognition.stop();
        _recognition = null;
        return;
      }

      _recognition = new SpeechRecognition();
      _recognition.lang      = 'en-US';
      _recognition.interimResults = false;
      _recognition.maxAlternatives = 1;

      voiceBtn.classList.add('voice-active');
      if (voiceIcon) { voiceIcon.className = 'bi bi-mic-fill'; }
      if (voiceRow)  { voiceRow.style.display = 'flex'; openDropdown(); }

      _recognition.onresult = e => {
        const transcript = e.results[0][0].transcript;
        const inp = document.getElementById('searchInput');
        if (inp) { inp.value = transcript; syncPlaceholder(); }
        const clr = document.getElementById('clearBtn');
        if (clr) clr.classList.remove('d-none');
        stopVoice();
        runSearch();
      };

      _recognition.onerror = _recognition.onend = () => stopVoice();
      _recognition.start();
    });
  }
}

function stopVoice() {
  if (_recognition) { try { _recognition.stop(); } catch(_) {} _recognition = null; }
  if (voiceBtn)  voiceBtn.classList.remove('voice-active');
  if (voiceIcon) voiceIcon.className = 'bi bi-mic';
  if (voiceRow)  voiceRow.style.display = 'none';
  closeDropdown();
}

/* ═══════════════════════════════════════════════════════
   SHOP LINKS — BUY BUTTONS
   ═══════════════════════════════════════════════════════ */

function buildShopButtons(links, compact = false) {
  if (!links || (!links.daraz && !links.amazon && !links.custom)) {
    return compact ? '' :
      `<span class="text-body-tertiary" style="font-size:11px"><i class="bi bi-bag-x me-1"></i>Not available online</span>`;
  }
  const size = compact ? 'btn-xs' : 'btn-sm';
  let btns = '';
  if (links.daraz) {
    btns += `<a href="${links.daraz}" target="_blank" rel="noopener"
      class="btn ${size} btn-daraz" onclick="event.stopPropagation()">
      <span class="shop-logo-d">D</span> Daraz
    </a>`;
  }
  if (links.amazon) {
    btns += `<a href="${links.amazon}" target="_blank" rel="noopener"
      class="btn ${size} btn-amazon" onclick="event.stopPropagation()">
      <span class="shop-logo-a">A</span> Amazon
    </a>`;
  }
  if (links.custom) {
    btns += `<a href="${links.custom}" target="_blank" rel="noopener"
      class="btn ${size} btn-custom" onclick="event.stopPropagation()">
      <i class="bi bi-bag-check me-1"></i>${links.custom_label || 'Buy Now'}
    </a>`;
  }
  return btns;
}

