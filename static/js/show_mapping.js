// ============================================================
// SHOW MAPPING PAGE – Complete Script
// Depends on: mapping_utils.js (loaded first)
// ============================================================

// ============================================================
// DATA HELPERS
// ============================================================

// ===== Get data from HTML data attributes =====
function getPageData() {
    const el = document.getElementById('page-data');
    if (!el) return null;

    try {
        return {
            supplierId: parseInt(el.dataset.supplierId),
            supplierName: el.dataset.supplierName,
            targetFields: JSON.parse(el.dataset.targetFields || '[]'),
            sourceFields: JSON.parse(el.dataset.sourceFields || '[]'),
            supplierMappings: JSON.parse(el.dataset.supplierMappings || '{}')
        };
    } catch (e) {
        console.error('❌ Failed to parse page data:', e);
        return null;
    }
}

// ============================================================
// UI HELPERS
// ============================================================

// ===== Mark Dirty =====
function markDirty() {
    hasChanges = true;
    updateSaveButton();
}

// ===== Show Toast =====
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
    if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();
    } else {
        setTimeout(() => toast.remove(), 3000);
    }
}

// ============================================================
// EVENT LISTENERS
// ============================================================

function attachEventListeners() {
    // Source select changes
    document.querySelectorAll('.source-select').forEach(select => {
        select.removeEventListener('change', onSourceChange);
        select.addEventListener('change', onSourceChange);
    });

    // Mandatory checkbox changes
    document.querySelectorAll('.mandatory-check').forEach(checkbox => {
        checkbox.removeEventListener('change', onMandatoryChange);
        checkbox.addEventListener('change', onMandatoryChange);
    });

    // Prepopulated input changes
    document.querySelectorAll('.prepopulated-value').forEach(input => {
        input.removeEventListener('input', onPrepopulatedInput);
        input.addEventListener('input', onPrepopulatedInput);
    });
}

function onSourceChange() {
    const targetName = this.dataset.targetName;
    const sourceColumn = this.value === '' ? null : this.value;
    if (currentMappings[targetName]) {
        currentMappings[targetName].source_field = sourceColumn;
    }
    markDirty();
}

function onMandatoryChange() {
    const targetId = parseInt(this.dataset.targetId);
    const targetName = this.closest('tr').querySelector('.source-select').dataset.targetName;
    if (currentMappings[targetName]) {
        currentMappings[targetName].is_mandatory = this.checked;
    }
    updateMandatorySummary();
    markDirty();
}

function onPrepopulatedInput() {
    const targetId = parseInt(this.dataset.targetId);
    const targetName = this.closest('tr').querySelector('.source-select').dataset.targetName;
    if (currentMappings[targetName]) {
        currentMappings[targetName].prepopulated_value = this.value.trim();
    }
    markDirty();
}

// ============================================================
// MANDATORY SUMMARY
// ============================================================

function updateMandatorySummary() {
    const summaryDiv = document.getElementById('mandatorySummary');
    const listSpan = document.getElementById('mandatoryList');
    const mandatoryChecks = document.querySelectorAll('.mandatory-check:checked');

    if (mandatoryChecks.length > 0) {
        const names = [];
        mandatoryChecks.forEach(cb => {
            const row = cb.closest('tr');
            if (row) {
                const nameEl = row.querySelector('td strong');
                if (nameEl) names.push(nameEl.textContent);
            }
        });
        if (names.length > 0) {
            summaryDiv.style.display = 'block';
            listSpan.innerHTML = names.map(n =>
                `<span class="badge bg-danger me-1">${n}</span>`
            ).join('');
        }
    } else {
        summaryDiv.style.display = 'none';
    }
}


// ============================================================
// DELETE SUPPLIER
// ============================================================

async function deleteSupplier(supplierId, supplierName) {
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
        showToast('Success', `Supplier "${supplierName}" deleted successfully`, 'success');
        setTimeout(() => window.location.href = '/mappings-list', 1500);
    } catch (e) {
        console.error('Delete error:', e);
        showToast('Error', `Failed to delete supplier: ${e.message}`, 'danger');
    }
}

// ============================================================
// INIT
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    renderMappingUI();
});