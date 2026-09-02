// ===== State =====
let mappings = [];

// ===== API Calls =====
async function fetchMappings() {
    const r = await fetch('/api/mappings-list');
    if (!r.ok) throw new Error('Failed to fetch mappings list');
    return r.json();
}

// ===== Delete Supplier =====
async function deleteSupplier(supplierId, supplierName) {
    // ✅ Show confirmation dialog
    const confirmed = confirm(
        `⚠️ Are you sure you want to delete supplier "${supplierName}" and all associated mappings?\n\nThis action cannot be undone!`
    );

    if (!confirmed) return;

    try {
        const response = await fetch(`/api/suppliers/${supplierId}`, {
            method: 'DELETE',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete supplier');
        }

        // ✅ Show success toast
        showToast('Success', `Supplier "${supplierName}" deleted successfully`, 'success');

        // ✅ Refresh the list
        renderMappings();

    } catch (e) {
        console.error('Delete error:', e);
        showToast('Error', `Failed to delete supplier: ${e.message}`, 'danger');
    }
}

// ===== Render List =====
async function renderMappings() {
    const grid = document.getElementById('mappingGrid');
    grid.innerHTML = `<div class="col-12 text-center py-4"><div class="spinner-border text-primary"></div><p>Loading...</p></div>`;
    try {
        const data = await fetchMappings();
        const suppliers = data.suppliers || [];

        if (!suppliers.length) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="bi bi-inbox fs-1 text-muted"></i>
                    <h5 class="mt-3">No suppliers found</h5>
                    <p class="text-muted">Add a supplier via CLI to create a supplier.</p>
                </div>`;
            return;
        }

        let html = '';
        for (const [id, name] of suppliers) {
            html += `
                <div class="col-md-3 col-sm-6">
                    <div class="card mapping-card">
                        <div class="card-body text-center">
                            <i class="bi bi-building fs-1 text-primary"></i>
                            <h5 class="card-title mt-2">${name}</h5>
                            <div class="d-flex justify-content-center gap-2 mt-3">
                                <button class="btn btn-sm btn-outline-primary" onclick="navigateToDetail('${id}')">
                                    <i class="bi bi-eye"></i> View
                                </button>
                                <button class="btn btn-sm btn-outline-danger" onclick="deleteSupplier('${id}', '${name}')">
                                    <i class="bi bi-trash"></i> Delete
                                </button>
                            </div>
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
function navigateToDetail(supplier_id) {
    window.location.href = `/show-mapping/${encodeURIComponent(supplier_id)}`;
}

// ===== Refresh =====
function refreshMappings() {
    renderMappings();
}

// ===== Toast Notification (if not already defined) =====
function showToast(title, message, type = 'success') {
    const colors = {
        success: 'bg-success',
        danger: 'bg-danger',
        warning: 'bg-warning',
        info: 'bg-info'
    };

    const container = document.querySelector('.toast-container') || (() => {
        const el = document.createElement('div');
        el.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(el);
        return el;
    })();

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white border-0 ${colors[type] || colors.info}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body"><strong>${title}</strong> — ${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', renderMappings);