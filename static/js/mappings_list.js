// ===== State =====
let mappings = [];
let currentMapping = null;


// ===== API Calls =====
async function fetchMappings() {
    const r = await fetch('/api/mappings-list');
    if (!r.ok) throw new Error('Failed to fetch mappings list');
    return r.json();
}

async function fetchMapping(m) {
    const r = await fetch(`/api/mappings/${m}`);
    if (!r.ok) throw new Error('Failed to fetch mapping');
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
                    <div class="card mapping-card" onclick="showDetail('${m}')">
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

// ===== Show Detail =====
async function showDetail(mapping) {
    currentMapping = mapping;
    document.getElementById('listView').style.display = 'none';
    document.getElementById('detailView').style.display = 'block';
    document.getElementById('detailTitle').innerHTML = `<strong>${mapping}</strong>`;
    const content = document.getElementById('detailContent');
    const count = document.getElementById('detailCount');
    content.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;

    try {
        const data = await fetchMapping(mapping);

        // ✅ New response structure: data.mappings is an array, not an object
        const mappingsList = data.mappings || [];
        const totalMappings = data.total_mappings || mappingsList.length;

        count.textContent = `${totalMappings} mapping${totalMappings !== 1 ? 's' : ''}`;

        if (!mappingsList.length) {
            content.innerHTML = `<div class="text-center py-5"><i class="bi bi-diagram-3 fs-1 text-muted"></i><h5 class="mt-3">No mappings for ${mapping}</h5></div>`;
            return;
        }

        // ✅ Build table with all fields
        let table = `
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Source Field</th>
                            <th style="width:30px;"></th>
                            <th>Target Field</th>
                            <th>Mandatory</th>
                            <th>Status</th>
                            <th>Prepopulated Value</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        mappingsList.forEach((item, i) => {
            const sourceDisplay = item.source_field || '—';
            const targetDisplay = item.target_field || '—';
            const mandatoryDisplay = item.is_mandatory ? '✅ Yes' : '❌ No';
            const statusDisplay = item.is_active ? 'Active' : 'Inactive';
            const prepopulatedDisplay = item.prepopulated_value || '—';

            table += `
                <tr>
                    <td>${i + 1}</td>
                    <td><code>${sourceDisplay}</code></td>
                    <td><i class="bi bi-arrow-right text-primary"></i></td>
                    <td><code>${targetDisplay}</code></td>
                    <td>${mandatoryDisplay}</td>
                    <td><span class="badge ${item.is_active ? 'bg-success' : 'bg-secondary'}">${statusDisplay}</span></td>
                    <td>${prepopulatedDisplay}</td>
                </tr>
            `;
        });

        table += `</tbody></table></div>`;
        content.innerHTML = table;

        history.pushState({ mapping }, '', `/mappings-list/${mapping}`);

    } catch (e) {
        content.innerHTML = `<div class="text-danger">❌ ${e.message}</div>`;
    }
}

// ===== Show List View =====
function showListView() {
    currentMapping = null;
    document.getElementById('listView').style.display = 'block';
    document.getElementById('detailView').style.display = 'none';
    history.pushState(null, '', '/mappings-list');
    renderMappings();
}

// ===== Refresh =====
function refreshMappings() {
    renderMappings();
}

// ===== Browser Back/Forward =====
window.addEventListener('popstate', function (e) {
    if (e.state && e.state.mapping) {
        showDetail(e.state.mapping);
    } else {
        showListView();
    }
});

// ===== Init =====
document.addEventListener('DOMContentLoaded', function () {
    // Check if we're on a detail page (URL contains /mappings-list/name)
    if (window.location.pathname.startsWith('/mappings-list/')) {
        const s = decodeURIComponent(window.location.pathname.split('/')[2]);
        if (s) {
            showDetail(s);
            return;
        }
    }
    // Otherwise show the list
    renderMappings();
});