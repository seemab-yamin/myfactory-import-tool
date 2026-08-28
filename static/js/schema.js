async function loadSchema() {
    const container = document.getElementById('schemaContent');
    container.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;

    try {
        const response = await fetch('/api/schema');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSchema(data, container);  // ← Pass container here
        document.getElementById('lastUpdated').textContent = new Date().toLocaleString();
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger">
                <strong>❌ Error:</strong> ${error.message}
                <br><button class="btn btn-primary btn-sm mt-2" onclick="loadSchema()">Retry</button>
            </div>
        `;
    }
}

function renderSchema(data, container) {  // ← Accept container as parameter
    let html = '';
    const entries = Object.entries(data);

    if (entries.length === 0) {
        container.innerHTML = `<div class="alert alert-warning">⚠️ No tables found.</div>`;
        return;
    }

    for (const [tableName, columns] of entries) {
        html += `<h2 class="mt-4">📋 ${tableName}</h2>`;
        if (!columns || columns.length === 0) {
            html += `<div class="alert alert-warning">⚠️ Table '${tableName}' not found or has no columns.</div>`;
            continue;
        }
        html += `
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead><tr><th>#</th><th>Column</th><th>Type</th><th>Nullable</th><th>PK</th></tr></thead>
                    <tbody>`;
        columns.forEach((col, i) => {
            html += `<tr>
                <td>${i + 1}</td>
                <td><strong>${col.name || ''}</strong></td>
                <td><code>${col.type || ''}</code></td>
                <td>${col.nullable !== false ? '✅' : '❌'}</td>
                <td>${col.primary_key ? '🔑' : ''}</td>
            </tr>`;
        });
        html += `</tbody></table></div>
            <p class="text-muted">Total: <strong>${columns.length}</strong> columns</p>
        `;
    }
    container.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', loadSchema);