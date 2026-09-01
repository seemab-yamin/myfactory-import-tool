// ===== State =====
let mappings = [];

// ===== API Calls =====
async function fetchMappings() {
    const r = await fetch('/api/mappings-list');
    if (!r.ok) throw new Error('Failed to fetch mappings list');
    return r.json();
}

// ===== Render List =====
async function renderMappings() {
    const grid = document.getElementById('mappingGrid');
    grid.innerHTML = `<div class="col-12 text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;
    try {
        const data = await fetchMappings();
        mappings = data.mappings || [];
        if (!mappings.length) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="bi bi-inbox fs-1 text-muted"></i>
                    <h5 class="mt-3">No mappings found</h5>
                    <p class="text-muted">Add a mapping via CLI to create a mapping.</p>
                </div>`;
            return;
        }
        let html = '';
        for (const m of mappings) {
            html += `
                <div class="col-md-3 col-sm-6">
                    <div class="card mapping-card" onclick="navigateToDetail('${m}')">
                        <div class="card-body text-center">
                            <i class="bi bi-building fs-1 text-primary"></i>
                            <h5 class="card-title mt-2">${m}</h5>
                        </div>
                    </div>
                </div>`;
        }
        grid.innerHTML = html;
    } catch (e) {
        grid.innerHTML = `<div class="col-12 text-center text-danger">❌ ${e.message}<br><button class="btn btn-primary btn-sm mt-2" onclick="renderMappings()">Retry</button></div>`;
    }
}

// ===== Navigate to Detail =====
function navigateToDetail(mapping) {
    window.location.href = `/mappings-list/${encodeURIComponent(mapping)}`;
}

// ===== Refresh =====
function refreshMappings() {
    renderMappings();
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', renderMappings);