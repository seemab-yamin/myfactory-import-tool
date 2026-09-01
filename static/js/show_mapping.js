// ===== State =====
let currentMapping = null;

// ===== API Calls =====
async function fetchMapping(m) {
    const r = await fetch(`/api/mappings/${m}`);
    if (!r.ok) throw new Error('Failed to fetch mapping');
    return r.json();
}

// ===== Show Detail =====
async function showDetail(mapping) {
    currentMapping = mapping;
    const content = document.getElementById('detailContent');
    const count = document.getElementById('detailCount');
    content.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;

    try {
        const data = await fetchMapping(mapping);
        const mappingsList = data.mappings || [];
        const totalMappings = data.total_mappings || mappingsList.length;

        count.textContent = `${totalMappings} mapping${totalMappings !== 1 ? 's' : ''}`;

        if (!mappingsList.length) {
            content.innerHTML = `<div class="text-center py-5"><i class="bi bi-diagram-3 fs-1 text-muted"></i><h5 class="mt-3">No mappings for ${mapping}</h5></div>`;
            return;
        }

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

    } catch (e) {
        content.innerHTML = `<div class="text-danger">❌ ${e.message}</div>`;
    }
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', function () {
    // Get supplier name from URL
    const pathParts = window.location.pathname.split('/');
    const supplier = decodeURIComponent(pathParts[pathParts.length - 1]);
    if (supplier) {
        showDetail(supplier);
    }
});