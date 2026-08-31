// ============================================================
//  Schema Viewer - Complete Fixed Script
// ============================================================

async function loadSchema(useCache = true) {
    const container = document.getElementById('schemaContent');
    container.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;

    try {
        const cacheParam = (useCache === true || useCache === false) ? useCache : true;
        const url = `/api/schema?use_cache=${cacheParam}&simplified=false`;
        console.log('🔍 Fetching schema with use_cache:', cacheParam);

        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSchema(data, container);
        document.getElementById('lastUpdated').textContent = new Date().toLocaleString();
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger">
                <strong>❌ Error:</strong> ${error.message}
                <br><button class="btn btn-primary btn-sm mt-2" onclick="loadSchema(true)">Retry</button>
            </div>
        `;
    }
}

function renderSchema(data, container) {
    let html = '';
    let entries = [];

    // 🔍 Log what we received
    console.log('📦 renderSchema received:', data);

    // Check if data is the new format with columns array
    if (data && data.columns) {
        if (Array.isArray(data.columns)) {
            // ✅ Good: columns is an array
            entries = [[data.table_name || 'Table', data.columns]];
        } else {
            // ❌ columns is not an array — log it and try to fix
            console.warn('⚠️ data.columns is not an array:', data.columns);
            if (typeof data.columns === 'object' && data.columns !== null) {
                const values = Object.values(data.columns);
                if (values.length > 0 && typeof values[0] === 'object') {
                    entries = [[data.table_name || 'Table', values]];
                }
            }
        }
    } else if (data && typeof data === 'object' && !Array.isArray(data)) {
        const objectEntries = Object.entries(data);
        entries = objectEntries.filter(([key, value]) => Array.isArray(value));
    } else if (Array.isArray(data)) {
        entries = [['Table', data]];
    }
    if (entries.length === 0) {
        container.innerHTML = `
            <div class="alert alert-warning">
                ⚠️ No tables found. Raw data: 
                <pre>${JSON.stringify(data, null, 2)}</pre>
            </div>
        `;
        return;
    }
    for (const [tableName, columns] of entries) {
        html += `<h2 class="mt-4">📋 ${tableName}</h2>`;
        if (!columns || !Array.isArray(columns) || columns.length === 0) {
            html += `<div class="alert alert-warning">⚠️ Table '${tableName}' has no columns.</div>`;
            continue;
        }
        html += `
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Column</th>
                            <th>Type</th>
                            <th>Nullable</th>
                        </tr>
                    </thead>
                    <tbody>`;
        columns.forEach((col, i) => {
            html += `<tr>
                <td>${i + 1}</td>
                <td><strong>${col.name || ''}</strong></td>
                <td><code>${col.type || ''}</code></td>
                <td>${col.nullable !== false ? '✅' : '❌'}</td>
            </tr>`;
        });
        html += `</tbody></table></div>
            <p class="text-muted">Total: <strong>${columns.length}</strong> columns</p>
        `;
    }
    container.innerHTML = html;
}

async function refreshSchemaData() {
    const container = document.getElementById('schemaContent');
    const btn = document.getElementById('refreshSchemaBtn');
    // Disable button & show spinner
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Refreshing...';
    }
    container.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Force refreshing schema...</p></div>`;
    try {
        const response = await fetch('/api/schema?refresh_cache=true&use_cache=false');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        console.log('🔄 Schema refreshed:', data);

        // Render the fresh data
        renderSchema(data, container);
        document.getElementById('lastUpdated').textContent = new Date().toLocaleString();

        showToast('Schema refreshed successfully', 'success');
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger">
                <strong>❌ Error:</strong> ${error.message}
                <br><button class="btn btn-primary btn-sm mt-2" onclick="refreshSchemaData()">Retry</button>
            </div>
        `;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Force Refresh';
        }
    }
}

// ============================================================
//  Toast Notification (if showToast is not defined elsewhere)
// ============================================================
function showToast(message, type = 'success') {
    const colors = {
        success: 'bg-success text-white',
        danger: 'bg-danger text-white',
        warning: 'bg-warning text-dark',
        info: 'bg-info text-white'
    };

    const toastContainer = document.querySelector('.toast-container') || (() => {
        const el = document.createElement('div');
        el.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(el);
        return el;
    })();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center border-0 ${colors[type] || colors.info}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}
// ============================================================
//  Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', function () {
    // Load schema with cache enabled by default
    loadSchema(true);
});