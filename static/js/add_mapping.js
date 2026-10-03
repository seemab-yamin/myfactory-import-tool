/**
 * add_supplier.js
 *
 * Handles the Add Supplier workflow:
 *   Step 1: Supplier name (unique)
 *   Step 2: Upload sample file (CSV/Excel) + sheet selection + header row
 *   Step 3: Map target fields → source fields
 */

// ============================================================
// STATE
// ============================================================
let parsedFileColumns = [];
let parsedColumns = [];
let mandatoryFields = [];
let currentMappings = {};
let prepopulatedValues = {};
let allSupplierNames = [];
let hasChanges = false;

// ✅ Parse-time config — attached to `window` so mapping_utils.js can read them
// across script-file boundaries (top-level `let` is script-scoped, not global).
window.parsedHeaderRowIndex = null;
window.parsedSheetName = null;
window.parsedDelimiter = null;

function getCurrentStep() {
    if (!step1Complete) return 1;
    if (!step2Complete) return 2;
    return 3;
}

// ============================================================
// AUTO-MAP VISUALS
// ============================================================
const AUTO_MAP_EXACT_TYPES = ['exact', 'case_insensitive', 'normalized'];

function applyAutoMapVisual(select, matchType) {
    if (AUTO_MAP_EXACT_TYPES.includes(matchType)) {
        select.classList.add('auto-mapped-exact');
        select.title = `Auto-mapped (${matchType})`;
    } else if (matchType === 'fuzzy') {
        select.classList.add('auto-mapped-fuzzy');
        select.title = 'Fuzzy match — please verify';
        // Add warning icon right after the select (once)
        const parent = select.parentElement;
        if (parent && !parent.querySelector('.fuzzy-warning')) {
            const warn = document.createElement('span');
            warn.className = 'fuzzy-warning';
            warn.textContent = ' ⚠️';
            warn.title = 'Fuzzy match — please verify';
            parent.appendChild(warn);
        }
    }
}

function applySuggestions(suggestions) {
    const entries = Object.entries(suggestions || {});
    if (entries.length === 0) return;

    entries.forEach(([targetFieldName, matchInfo]) => {
        if (!matchInfo || typeof matchInfo !== 'object') return;
        const sourceColumn = matchInfo.source_column;
        const matchType = matchInfo.match_type || 'exact';
        if (!sourceColumn) return;

        const select = document.querySelector(
            `.source-select[data-target-name="${CSS.escape(targetFieldName)}"]`
        );
        if (!select) return;

        // ✅ Do NOT overwrite user's manual choice
        const currentVal = select.value;
        const isUntouched = !currentVal || currentVal === 'None';
        if (!isUntouched) return;

        const optionExists = Array.from(select.options)
            .some(opt => opt.value === sourceColumn);
        if (!optionExists) return;

        select.value = sourceColumn;
        applyAutoMapVisual(select, matchType);
        select.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // ✅ Re-sort: unmatched rows to top, matched rows to bottom
    reorderMappingRows();
}

function renderAutoMapSummary(summary) {
    const banner = document.getElementById('autoMapSummary');
    const text = document.getElementById('autoMapSummaryText');
    if (!banner || !text) return;

    const s = summary || {};

    // Confirmed = deterministic matches (exact + case_insensitive + normalized)
    const confirmed =
        (s.exact || 0) +
        (s.case_insensitive || 0) +
        (s.normalized || 0);

    // Fuzzy = fuzzy suggestions
    const fuzzy = s.fuzzy || 0;

    // Unmatched = targets left without any suggestion
    const unmatched = s.unmatched_targets || 0;

    text.innerHTML =
        `<strong>Auto-mapped:</strong> ` +
        `<span class="text-success">${confirmed} confirmed</span> | ` +
        `<span class="text-warning">${fuzzy} fuzzy suggestions</span> | ` +
        `<span class="text-muted">${unmatched} unmatched</span>`;

    banner.classList.remove('d-none');
}

function reorderMappingRows() {
    const tbody = document.getElementById('mappingTableBody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    if (rows.length === 0) return;

    const unmatched = [];
    const matched = [];

    rows.forEach(row => {
        const select = row.querySelector('.source-select');
        if (!select) return;
        const val = select.value;
        const isUnmatched = !val || val === 'None';
        (isUnmatched ? unmatched : matched).push(row);
    });

    // Clear + re-append in new order
    tbody.innerHTML = '';
    unmatched.forEach(r => tbody.appendChild(r));
    matched.forEach(r => tbody.appendChild(r));
}

function showAutoMapSummary(data) {
    const statusDiv = document.getElementById('autoMapStatus');
    if (!statusDiv) return;

    const s = data.summary || {};
    const matched = Object.keys(data.suggestions || {}).length;
    const unmatchedTargets = (data.unmatched_targets || []).length;
    const total = matched + unmatchedTargets;

    const parts = [];
    if (s.exact) parts.push(`exact: ${s.exact}`);
    if (s.case_insensitive) parts.push(`case-insensitive: ${s.case_insensitive}`);
    if (s.normalized) parts.push(`normalized: ${s.normalized}`);
    if (s.fuzzy) parts.push(`fuzzy: ${s.fuzzy}`);
    const breakdown = parts.length
        ? ` <span class="text-secondary small">(${parts.join(', ')})</span>`
        : '';

    statusDiv.innerHTML =
        `<span class="text-success">✅ Auto-mapped ${matched} of ${total} fields.</span> ` +
        `<span class="text-muted">${unmatchedTargets} need manual mapping.</span>` +
        breakdown;
}

// ============================================================
// SUPPLIER UNIQUENESS
// ============================================================
async function fetchAllSuppliers() {
    try {
        const response = await fetch('/api/suppliers');
        if (!response.ok) throw new Error('Failed to fetch suppliers');
        const data = await response.json();
        const suppliers = data.suppliers || [];
        allSupplierNames = suppliers.map(s => (s[1] || '').toLowerCase()).filter(Boolean);
        return allSupplierNames;
    } catch (e) {
        console.warn('Could not fetch suppliers:', e);
        allSupplierNames = [];
        return [];
    }
}

function checkSupplierName() {
    const input = document.getElementById('supplierName');
    const feedback = document.getElementById('supplierNameFeedback');
    const name = input.value.trim().toLowerCase();

    if (!name) {
        input.classList.remove('is-invalid', 'is-valid');
        supplierExists = false;
        if (feedback) feedback.textContent = '';
        updateStepStates();
        return;
    }

    const exists = allSupplierNames.includes(name);

    if (exists) {
        input.classList.add('is-invalid');
        input.classList.remove('is-valid');
        if (feedback) feedback.textContent = '⚠️ This supplier name already exists. Please choose a different name.';
        supplierExists = true;
    } else {
        input.classList.remove('is-invalid');
        input.classList.add('is-valid');
        if (feedback) feedback.textContent = '✅ Name is available';
        supplierExists = false;
    }

    updateStepStates();
}

/**
 * Wrapper: reads DOM inputs, calls parseFileOnly(), applies UI effects
 * via parseRender(), then updates mapping UI + status + step state.
 */
async function parseSampleFile() {
    const statusDiv = document.getElementById('parseStatus');

    statusDiv.innerHTML = '<span class="text-info">⏳ Uploading & parsing...</span>';
    parseFileBtn.disabled = true;

    try {
        // Render preview + set window.* state
        await parseRender();
        // Build mapping UI + status
        buildMappingUI(targetColumns, parsedColumns);
        // Enable Auto-Map button now that columns are parsed
        if (autoMapBtn) autoMapBtn.disabled = false;
        if (autoMapStatus) autoMapStatus.innerHTML = '';
        clearAutoMapVisuals();

        // Hide the summary banner (fresh file, old counts no longer valid)
        const banner = document.getElementById('autoMapSummary');
        if (banner) banner.classList.add('d-none');

        statusDiv.innerHTML = `<span class="text-success">✅ Parsed ${parsedColumns.length} columns</span>`;
        showToast('Success', `Parsed ${parsedColumns.length} columns`, 'success');
    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
    } finally {
        parseFileBtn.disabled = false;
        updateStepStates();
    }
}

// ============================================================
// FETCH TARGET SCHEMA
// ============================================================
async function fetchTargetSchema() {
    try {
        const response = await fetch('/api/schema');
        if (!response.ok) throw new Error('Failed to fetch schema');
        const data = await response.json();

        const allColumns = data.columns || data.tdProducts || [];
        const excluded = ['ProductID'];
        targetColumns = allColumns.filter(c => !excluded.includes(c.name));

        mandatoryFields = targetColumns
            .filter(c => c.nullable === false)
            .map(c => c.target_field_id);

        return targetColumns;
    } catch (e) {
        console.error('Error fetching schema:', e);
        showToast('Error', 'Failed to load product schema', 'danger');
        return [];
    }
}


// ============================================================
// AUTO-MAP FIELDS
// ============================================================
async function autoMapFields() {
    const statusDiv = document.getElementById('autoMapStatus');
    const btn = document.getElementById('autoMapBtn');

    if (!parsedFileColumns || parsedFileColumns.length === 0) {
        showToast('Warning', 'Upload and parse a file first.', 'warning');
        return;
    }

    // Clear previous visuals before re-applying
    clearAutoMapVisuals();

    btn.disabled = true;
    statusDiv.innerHTML = '<span class="text-info">⏳ Fetching suggestions...</span>';

    try {
        const response = await fetch('/api/mappings-auto-suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_columns: parsedFileColumns,
                table_name: 'tdProducts',
            }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        applySuggestions(data.suggestions || {});
        showAutoMapSummary(data);
        renderAutoMapSummary(data.summary);
    } catch (e) {
        console.error('autoMapFields failed:', e);
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', `Auto-map failed: ${e.message}`, 'danger');
    } finally {
        btn.disabled = false;
    }
}

// ============================================================
// EVENT HANDLERS
// ============================================================
function handleSourceChange() {
    const targetId = parseInt(this.dataset.targetId, 10);

    // If user manually changes the select, remove the auto-map visual
    this.classList.remove('auto-mapped-exact', 'auto-mapped-fuzzy');
    this.removeAttribute('title');
    const parent = this.parentElement;
    if (parent) {
        const warn = parent.querySelector('.fuzzy-warning');
        if (warn) warn.remove();
    }

    updateMapping(targetId, this.value);
    markDirty();
}

function handleMandatoryChange() {
    const targetId = parseInt(this.dataset.targetId, 10);
    const col = window.targetColumns?.find(c => c.target_field_id === targetId);

    if (this.checked) {
        if (!mandatoryFields.includes(targetId)) mandatoryFields.push(targetId);
    } else {
        if (col && col.nullable === false) {
            this.checked = true;
            showToast('Warning', 'This field is required and cannot be made optional', 'warning');
            return;
        }
        mandatoryFields = mandatoryFields.filter(id => id !== targetId);
    }
    updateValidation(targetId);
    markDirty();
}

function handlePrepopulatedInput() {
    const targetId = parseInt(this.dataset.targetId, 10);
    const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);
    const val = this.value.trim();

    if (val) prepopulatedValues[targetId] = val;
    else delete prepopulatedValues[targetId];

    updateMapping(targetId, sourceSelect ? sourceSelect.value : null);
    markDirty();
}

// ============================================================
// UI UPDATES
// ============================================================
function updateMapping(targetId, sourceColumn) {
    const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);
    const prepopulatedInput = document.querySelector(`.prepopulated-value[data-target-id="${targetId}"]`);
    const targetName = sourceSelect ? sourceSelect.dataset.targetName : null;

    const hasSource = sourceColumn && sourceColumn !== '' && sourceColumn !== 'None';
    const hasPrepop = prepopulatedInput && prepopulatedInput.value.trim() !== '';

    currentMappings[targetId] = {
        target: targetName,
        source: hasSource ? sourceColumn : null,
        prepopulated: hasPrepop,
        prepopulated_value: hasPrepop ? prepopulatedInput.value.trim() : null,
        target_id: targetId,
    };

    updateValidation(targetId);
    updateMappingStatus();
}

function updateValidation(targetId) {
    const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);
    const valueInput = document.querySelector(`.prepopulated-value[data-target-id="${targetId}"]`);
    const isMandatory = mandatoryFields.includes(targetId);

    if (sourceSelect) sourceSelect.classList.remove('is-invalid', 'is-valid');
    if (valueInput) valueInput.classList.remove('is-invalid', 'is-valid');

    if (!isMandatory) return;

    const hasSource = sourceSelect && sourceSelect.value && sourceSelect.value !== 'None';
    const hasPrepop = valueInput && valueInput.value.trim() !== '';

    if (!hasSource && !hasPrepop) {
        if (sourceSelect) sourceSelect.classList.add('is-invalid');
        if (valueInput) valueInput.classList.add('is-invalid');
    } else if (sourceSelect && hasSource) {
        sourceSelect.classList.add('is-valid');
    }
}

function updateMappingStatus() {
    const totalMapped = Object.keys(currentMappings).length;

    const mandatoryOk = mandatoryFields.every(id => {
        const m = currentMappings[id];
        if (!m) return false;
        return (m.source && m.source !== '') || (m.prepopulated && m.prepopulated_value);
    });

    const canSave = hasChanges && mandatoryOk && totalMapped > 0;
    saveBtn.disabled = !canSave;
}

function markDirty() {
    hasChanges = true;
    updateMappingStatus();
}

// ============================================================
// RESET
// ============================================================
function resetForm() {
    supplierNameInput.value = '';
    sampleFileInput.value = '';
    document.getElementById('parseStatus').innerHTML = '';
    document.getElementById('filePreview').style.display = 'none';
    mappingArea.style.display = 'none';
    noFileMessage.style.display = 'block';
    document.getElementById('saveStatus').innerHTML = '';
    saveBtn.disabled = true;

    supplierExists = false;
    parsedColumns = [];
    parsedFileColumns = [];
    currentMappings = {};
    prepopulatedValues = {};
    step1Complete = false;
    step2Complete = false;
    allSupplierNames = [];
    hasChanges = false;

    window.parsedHeaderRowIndex = null;
    window.parsedSheetName = null;
    window.parsedDelimiter = null;
    uploadedFilePath = null;

    if (delimiterInput) delimiterInput.value = ',';
    if (delimiterRow) delimiterRow.style.display = 'none';
    if (headerRowIndexInput) headerRowIndexInput.value = '1';

    // ✅ Reset auto-map UI
    if (autoMapBtn) autoMapBtn.disabled = true;
    if (autoMapStatus) autoMapStatus.innerHTML = '';
    clearAutoMapVisuals();

    // ✅ Hide the summary banner
    const banner = document.getElementById('autoMapSummary');
    if (banner) banner.classList.add('d-none');

    resetSheetState();
    updateStepStates();
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', async function () {
    await fetchTargetSchema();
    await fetchAllSuppliers();

    if (supplierNameInput) {
        supplierNameInput.addEventListener('input', checkSupplierName);
    }
    if (sheetSelect) {
        sheetSelect.addEventListener('change', function () {
            selectedSheet = this.value || null;
            updateStepStates();
        });
    }

    updateStepStates();
});