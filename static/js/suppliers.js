let suppliers = [];

async function fetchSuppliers() {
    const r = await fetch('/api/suppliers');
    if (!r.ok) throw new Error('Failed to fetch suppliers');
    return r.json();
}

async function fetchMappings(s) {
    const r = await fetch(`/api/mappings/${s}`);
    if (!r.ok) throw new Error('Failed to fetch mappings');
    return r.json();
}

async function renderSuppliers() {
    const grid = document.getElementById('supplierGrid');
    grid.innerHTML = `<div class="col-12 text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;
    try {
        const data = await fetchSuppliers();
        suppliers = data.suppliers || [];
        if (!suppliers.length) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="bi bi-inbox fs-1 text-muted"></i>
                    <h5 class="mt-3">No suppliers found</h5>
                    <p class="text-muted">Add a mapping via CLI to create a supplier.</p>
                </div>`;
            return;
        }
        let html = '';
        for (const s of suppliers) {
            let cnt = 0;
            try { cnt = (await fetchMappings(s)).summary?.total || 0; } catch (e) { }
            html += `
                <div class="col-md-3 col-sm-6">
                    <div class="card supplier-card" onclick="showDetail('${s}')">
                        <div class="card-body text-center">
                            <i class="bi bi-building fs-1 text-primary"></i>
                            <h5 class="card-title mt-2">${s}</h5>
                            <p class="card-text text-muted small">${cnt} mapping${cnt !== 1 ? 's' : ''}</p>
                        </div>
                    </div>
                </div>`;
        }
        grid.innerHTML = html;
    } catch (e) {
        grid.innerHTML = `<div class="col-12 text-center text-danger">❌ ${e.message}<br><button class="btn btn-primary btn-sm mt-2" onclick="renderSuppliers()">Retry</button></div>`;
    }
}

async function showDetail(supplier) {
    document.getElementById('listView').style.display = 'none';
    document.getElementById('detailView').style.display = 'block';
    document.getElementById('detailTitle').innerHTML = `<strong>${supplier}</strong>`;
    const content = document.getElementById('detailContent');
    const count = document.getElementById('detailCount');
    content.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;
    try {
        const data = await fetchMappings(supplier);
        const mappings = data.mappings || {};
        const entries = Object.entries(mappings);
        count.textContent = `${entries.length} mapping${entries.length !== 1 ? 's' : ''}`;
        if (!entries.length) {
            content.innerHTML = `<div class="text-center py-5"><i class="bi bi-diagram-3 fs-1 text-muted"></i><h5 class="mt-3">No mappings for ${supplier}</h5></div>`;
            return;
        }
        let table = `<div class="table-responsive"><table class="table table-striped"><thead><tr><th>#</th><th>Source</th><th>→</th><th>Target</th></tr></thead><tbody>`;
        entries.forEach(([src, tgt], i) => {
            table += `<tr><td>${i + 1}</td><td><code>${src}</code></td><td><i class="bi bi-arrow-right text-primary"></i></td><td><code>${tgt}</code></td></tr>`;
        });
        table += `</tbody></table></div>`;
        content.innerHTML = table;
        history.pushState({ supplier }, '', `/suppliers/${supplier}`);
    } catch (e) {
        content.innerHTML = `<div class="text-danger">❌ ${e.message}</div>`;
    }
}

function showListView() {
    document.getElementById('listView').style.display = 'block';
    document.getElementById('detailView').style.display = 'none';
    history.pushState(null, '', '/suppliers');
}

function refreshSuppliers() { renderSuppliers(); }

window.addEventListener('popstate', function (e) {
    if (e.state && e.state.supplier) showDetail(e.state.supplier);
    else showListView();
});

if (window.location.pathname.startsWith('/suppliers/')) {
    const s = decodeURIComponent(window.location.pathname.split('/')[2]);
    if (s) document.addEventListener('DOMContentLoaded', () => showDetail(s));
} else {
    document.addEventListener('DOMContentLoaded', renderSuppliers);
}