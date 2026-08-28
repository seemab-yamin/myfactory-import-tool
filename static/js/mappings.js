let allMappings = {};
let deleteTarget = null;

// ========== API Calls ==========
async function fetchAllMappings() {
    const response = await fetch('/api/mappings/all');
    if (!response.ok) throw new Error('Failed to fetch mappings');
    return response.json();
}

async function fetchSupplierMappings(supplier) {
    const response = await fetch(`/api/mappings/${supplier}`);
    if (!response.ok) throw new Error('Failed to fetch mappings');
    return response.json();
}

async function deleteMapping(supplier, sourceField) {
    const response = await fetch(`/api/mappings/${supplier}/${sourceField}`, {
        method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete mapping');
    return response.json();
}

async function saveMappingAPI(supplier, sourceField, targetField, active) {
    const formData = new FormData();
    formData.append('source_field', sourceField);
    formData.append('target_field', targetField);
    formData.append('active', active);

    const response = await fetch(`/api/mappings/${supplier}`, {
        method: 'POST',
        body: formData
    });
    if (!response.ok) throw new Error('Failed to save mapping');
    return response.json();
}

// ========== Render ==========
async function renderMappings() {
    const container = document.getElementById('mappingsContainer');

    try {
        const data = await fetchAllMappings();
        allMappings = data.mappings || {};

        if (Object.keys(allMappings).length === 0) {
            container.innerHTML = `
                    <div class="card">
                        <div class="card-body empty-state">
                            <div class="icon">🗺️</div>
                            <h5>No mappings found</h5>
                            <p class="text-muted">Create your first mapping by clicking the "Add Mapping" button.</p>
                            <button class="btn btn-primary btn-sm" onclick="showAddModal()">
                                <i class="bi bi-plus-circle"></i> Add Mapping
                            </button>
                        </div>
                    </div>
                `;
            return;
        }

        let html = '';
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();

        // Sort suppliers alphabetically
        const suppliers = Object.keys(allMappings).sort();

        for (const supplier of suppliers) {
            const mappings = allMappings[supplier] || {};
            const entries = Object.entries(mappings);

            // Filter by search
            const filtered = entries.filter(([source, target]) =>
                supplier.toLowerCase().includes(searchTerm) ||
                source.toLowerCase().includes(searchTerm) ||
                target.toLowerCase().includes(searchTerm)
            );

            if (filtered.length === 0 && searchTerm) continue;

            const total = entries.length;
            const activeCount = entries.filter(([_, target]) => target !== '').length;

            html += `
<div class="supplier-section" id="supplier-${supplier}">
    <div class="supplier-header" onclick="toggleSupplier('${supplier}')">
        <div>
            <strong><i class="bi bi-building"></i> ${supplier}</strong>
            <span class="badge bg-secondary ms-2">${total} mappings</span>
            <span class="badge bg-success ms-1">${activeCount} active</span>
        </div>
        <div>
            <button class="btn btn-sm btn-outline-success me-1" onclick="event.stopPropagation(); showAddModal('${supplier}')">
                <i class="bi bi-plus"></i>
            </button>
            <span class="badge bg-light"><i class="bi bi-chevron-down" id="chevron-${supplier}"></i></span>
        </div>
    </div>
    <div class="collapsible-content show" id="content-${supplier}">
        <div class="table-responsive">
            <table class="table table-striped table-hover table-mappings">
                <thead>
                    <tr>
                        <th style="width: 30px;">#</th>
                        <th>Source Field</th>
                        <th style="width: 40px;"></th>
                        <th>Target Field</th>
                        <th style="width: 80px;">Status</th>
                        <th style="width: 130px;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    `;

            filtered.forEach(([source, target], index) => {
                const isActive = target && target !== '';
                html += `
                    <tr class="mapping-row">
                        <td>${index + 1}</td>
                        <td><span class="source-field">${source}</span></td>
                        <td><i class="bi bi-arrow-right text-primary"></i></td>
                        <td><span class="target-field">${target || '<em class="text-muted">inactive</em>'}</span></td>
                        <td>
                            <span class="badge ${isActive ? 'badge-active' : 'badge-inactive'}">
                                ${isActive ? 'Active' : 'Inactive'}
                            </span>
                        </td>
                        <td>
                            <button class="btn btn-outline-primary btn-action" onclick="showEditModal('${supplier}', '${source}', '${target}')" title="Edit">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-action" onclick="showDeleteModal('${supplier}', '${source}')" title="Delete">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                    `;
            });

            html += `
                </tbody>
            </table>
        </div>
    </div>
</div>
`;
        }

        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = `
                <div class="card">
                    <div class="card-body text-center py-4 text-danger">
                        <i class="bi bi-exclamation-triangle fs-2"></i>
                        <p>Failed to load mappings: ${error.message}</p>
                        <button class="btn btn-primary btn-sm" onclick="renderMappings()">Retry</button>
                    </div>
                </div>
            `;
    }
}

// ========== Toggle Collapsible ==========
function toggleSupplier(supplier) {
    const content = document.getElementById(`content-${supplier}`);
    const chevron = document.getElementById(`chevron-${supplier}`);
    if (content) {
        content.classList.toggle('show');
        if (chevron) {
            chevron.className = content.classList.contains('show') ? 'bi bi-chevron-down' : 'bi bi-chevron-right';
        }
    }
}

// ========== Filter ==========
function filterMappings() {
    renderMappings();
}

// ========== Refresh ==========
function refreshAll() {
    renderMappings();
    showToast('Refreshed', 'Mappings reloaded', 'success');
}

// ========== Modal Functions ==========
let modalInstance = null;
let deleteModalInstance = null;

function showAddModal(supplier = '') {
    document.getElementById('modalTitle').textContent = 'Add Mapping';
    document.getElementById('modalSupplier').value = supplier || '';
    document.getElementById('modalSource').value = '';
    document.getElementById('modalTarget').value = '';
    document.getElementById('modalActive').checked = true;
    document.getElementById('editSupplier').value = '';
    document.getElementById('editSource').value = '';
    document.getElementById('modalSupplier').disabled = false;
    showModal();
}

function showEditModal(supplier, source, target) {
    document.getElementById('modalTitle').textContent = 'Edit Mapping';
    document.getElementById('modalSupplier').value = supplier;
    document.getElementById('modalSource').value = source;
    document.getElementById('modalTarget').value = target || '';
    document.getElementById('modalActive').checked = target && target !== '';
    document.getElementById('editSupplier').value = supplier;
    document.getElementById('editSource').value = source;
    document.getElementById('modalSupplier').disabled = true;
    showModal();
}

function showModal() {
    if (!modalInstance) {
        modalInstance = new bootstrap.Modal(document.getElementById('mappingModal'));
    }
    modalInstance.show();
}

function closeModal() {
    if (modalInstance) {
        modalInstance.hide();
    }
}

function showDeleteModal(supplier, source) {
    document.getElementById('deleteSupplier').textContent = supplier;
    document.getElementById('deleteSource').textContent = source;
    deleteTarget = { supplier, source };
    if (!deleteModalInstance) {
        deleteModalInstance = new bootstrap.Modal(document.getElementById('deleteModal'));
    }
    deleteModalInstance.show();
}

// ========== Save Mapping ==========
async function saveMapping() {
    const supplier = document.getElementById('modalSupplier').value.trim();
    const source = document.getElementById('modalSource').value.trim();
    const target = document.getElementById('modalTarget').value.trim();
    const active = document.getElementById('modalActive').checked;

    if (!supplier || !source || !target) {
        showToast('Error', 'All fields are required', 'danger');
        return;
    }

    const editSupplier = document.getElementById('editSupplier').value;
    const editSource = document.getElementById('editSource').value;

    try {
        // If editing, delete old mapping first
        if (editSupplier && editSource && (editSupplier !== supplier || editSource !== source)) {
            await deleteMapping(editSupplier, editSource);
        }

        await saveMappingAPI(supplier, source, target, active);
        closeModal();
        await renderMappings();
        showToast('Success', `Mapping saved: ${source} → ${target}`, 'success');
    } catch (error) {
        showToast('Error', `Failed to save mapping: ${error.message}`, 'danger');
    }
}

// ========== Confirm Delete ==========
async function confirmDelete() {
    if (!deleteTarget) return;

    try {
        await deleteMapping(deleteTarget.supplier, deleteTarget.source);
        if (deleteModalInstance) deleteModalInstance.hide();
        await renderMappings();
        showToast('Deleted', `Mapping ${deleteTarget.source} deleted`, 'success');
        deleteTarget = null;
    } catch (error) {
        showToast('Error', `Failed to delete: ${error.message}`, 'danger');
    }
}

// ========== Toast ==========
function showToast(title, message, type = 'info') {
    const container = document.querySelector('.toast-container');
    const colors = {
        success: 'bg-success',
        danger: 'bg-danger',
        info: 'bg-info',
        warning: 'bg-warning'
    };

    const toast = document.createElement('div');
    toast.className = 'toast align-items-center text-white border-0';
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    toast.innerHTML = `
<div class="d-flex ${colors[type] || 'bg-secondary'}">
    <div class="toast-body">
        <strong>${title}</strong> — ${message}
    </div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
</div>
`;
    container.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

// ========== Init ==========
document.addEventListener('DOMContentLoaded', renderMappings);
