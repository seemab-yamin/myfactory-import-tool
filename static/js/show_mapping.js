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

// ===== Update Save Button =====
function updateSaveButton() {
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) saveBtn.disabled = !hasChanges;
}

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
// SAVE MAPPINGS (using shared utils)
// ============================================================

async function saveMappings(supplierId) {
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('saveStatus');

    // Step 1: Collect current state from UI
    const currentState = collectMappingsFromUI();

    // Step 2: Detect changes
    const changes = detectChanges(currentState, initialMappings);

    if (changes.length === 0) {
        statusDiv.innerHTML = '<span class="text-info">ℹ️ No changes to save.</span>';
        showToast('Info', 'No changes to save', 'info');
        return;
    }

    // Step 3: Validate mandatory fields in the current state
    const mandatoryErrors = validateMandatoryFields(currentState);
    if (mandatoryErrors.length > 0) {
        highlightErrorRows(mandatoryErrors);
        renderValidationErrors(statusDiv, mandatoryErrors);
        showToast('Validation Error', `${mandatoryErrors.length} mandatory field(s) missing values.`, 'danger');
        scrollToFirstError();
        return;
    }

    // Step 4: Separate updates and deletions
    const toUpdate = changes.filter(c => !c.was_removed && (c.source_field || c.prepopulated_value));
    const toDelete = changes.filter(c => c.was_removed);

    // For prepopulated-only mappings, set unique source_field
    toUpdate.forEach(c => {
        if ((!c.source_field || c.source_field.trim() === '') && c.prepopulated_value) {
            c.source_field = `None`;
        }
    });

    // Step 5: Validate updates (duplicates, etc.)
    const updateErrors = validateMappings(toUpdate);
    if (updateErrors.length > 0) {
        highlightErrorRows(updateErrors);
        renderValidationErrors(statusDiv, updateErrors);
        showToast('Validation Error', `${updateErrors.length} error(s) found.`, 'danger');
        scrollToFirstError();
        return;
    }

    // ✅ At this point, all mandatory fields are valid, and we have real changes to apply.
    if (toUpdate.length === 0 && toDelete.length === 0) {
        // This should not happen now, but keep as safety
        statusDiv.innerHTML = '<span class="text-warning">⚠️ No valid mappings to save.</span>';
        showToast('Warning', 'No valid mappings to save.', 'warning');
        return;
    }

    console.log(`📦 Changes: ${toUpdate.length} update(s), ${toDelete.length} delete(s)`);

    saveBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-info">⏳ Saving ${toUpdate.length + toDelete.length} change(s)...</span>`;

    const supplierName = document.getElementById('detailTitle').textContent.trim();

    // Step 6: Save via API
    const results = await saveMappingsWithAPI(supplierName, toUpdate, toDelete, {
        onSuccess: (res) => {
            hasChanges = false;
            updateSaveButton();
            renderSaveResults(statusDiv, res);
            showToast('Success', `All ${res.successCount} changes saved successfully!`, 'success');
            window.location.reload();
        },
        onError: (res) => {
            renderSaveResults(statusDiv, res);
            showToast('Partial Save', `${res.successCount} succeeded, ${res.failureCount} failed.`, 'warning');
            saveBtn.disabled = false;
        }
    });
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