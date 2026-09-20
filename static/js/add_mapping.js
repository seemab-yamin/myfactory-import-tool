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
let targetColumns = [];
let mandatoryFields = [];
let currentMappings = {};
let initialMappings = {};
let supplierExists = false;
let prepopulatedValues = {};
let allSupplierNames = [];
let hasChanges = false;

// ✅ Parse-time config — attached to `window` so mapping_utils.js can read them
// across script-file boundaries (top-level `let` is script-scoped, not global).
window.parsedHeaderRowIndex = null;
window.parsedSheetName = null;
window.parsedDelimiter = null;

// ===== Step Unlock State =====
let step1Complete = false;
let step2Complete = false;

// Sheet fetch state
let availableSheets = [];
let selectedSheet = null;

// Temp file path returned by /api/parse-sheets (used for later parse)
let uploadedFilePath = null;

// ===== DOM References =====
const supplierNameInput = document.getElementById('supplierName');
const sampleFileInput = document.getElementById('sampleFile');
const parseFileBtn = document.getElementById('parseFileBtn');
const mappingArea = document.getElementById('mappingArea');
const noFileMessage = document.getElementById('noFileMessage');
const saveBtn = document.getElementById('saveBtn');
const fetchSheetsBtn = document.getElementById('fetchSheetsBtn');
const sheetSelectorRow = document.getElementById('sheetSelectorRow');
const sheetSelect = document.getElementById('sheetSelect');
const sheetStatus = document.getElementById('sheetStatus');
const fileTypeHint = document.getElementById('fileTypeHint');
const headerRowIndexInput = document.getElementById('headerRowIndex');
const delimiterRow = document.getElementById('delimiterRow');
const delimiterInput = document.getElementById('delimiterInput');

// ============================================================
// STEP MANAGEMENT
// ============================================================
function updateStepStates() {
    const name = supplierNameInput.value.trim();
    step1Complete = name.length > 0 && !supplierExists;

    sampleFileInput.disabled = !step1Complete;

    const hasFile = sampleFileInput.files.length > 0;
    const isExcel = hasFile && isExcelFile(sampleFileInput.files[0]);
    parseFileBtn.disabled = !step1Complete || !hasFile || (isExcel && !selectedSheet);

    if (fetchSheetsBtn) {
        fetchSheetsBtn.disabled = !isExcel;
    }

    const mappingSelects = document.querySelectorAll('.source-select');
    const prepopulatedInputs = document.querySelectorAll('.prepopulated-value');
    mappingSelects.forEach(s => (s.disabled = !step2Complete));
    prepopulatedInputs.forEach(i => (i.disabled = !step2Complete));

    updateStepIndicators();
}

function getCurrentStep() {
    if (!step1Complete) return 1;
    if (!step2Complete) return 2;
    return 3;
}

function updateStepIndicators() {
    document.querySelectorAll('[data-step]').forEach(card => {
        const step = parseInt(card.dataset.step);
        card.classList.toggle('active', step === getCurrentStep());
        card.classList.toggle('completed', step < getCurrentStep());
    });

    updateStepStatus(1, step1Complete, 'Enter supplier name', 'Name already exists');
    updateStepStatus(2, step2Complete, 'Upload a file', '');
}

function updateStepStatus(step, isComplete, pendingMsg, errorMsg) {
    const card = document.querySelector(`[data-step="${step}"]`);
    if (!card) return;

    const header = card.querySelector('.card-header');
    let statusEl = header.querySelector('.step-status');

    if (!statusEl) {
        statusEl = document.createElement('span');
        statusEl.className = 'step-status ms-2 badge';
        header.appendChild(statusEl);
    }

    if (isComplete) {
        statusEl.textContent = '✅ Complete';
        statusEl.className = 'step-status ms-2 badge bg-success';
    } else if (step === 1 && !step1Complete) {
        const name = supplierNameInput.value.trim();
        if (name.length === 0) {
            statusEl.textContent = '⏳ ' + pendingMsg;
            statusEl.className = 'step-status ms-2 badge bg-warning text-dark';
        } else if (supplierExists) {
            statusEl.textContent = '❌ ' + errorMsg;
            statusEl.className = 'step-status ms-2 badge bg-danger';
        }
    } else if (step === 2 && !step2Complete) {
        if (step1Complete) {
            statusEl.textContent = '⏳ ' + pendingMsg;
            statusEl.className = 'step-status ms-2 badge bg-warning text-dark';
        } else {
            statusEl.textContent = '🔒 Locked';
            statusEl.className = 'step-status ms-2 badge bg-secondary';
        }
    }
}

// ============================================================
// HELPERS
// ============================================================
function isExcelFile(file) {
    if (!file) return false;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    return ext === 'xlsx' || ext === 'xls';
}

function isCsvFile(file) {
    if (!file) return false;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    return ext === 'csv';
}

function getHeaderRowIndex() {
    const v = parseInt(headerRowIndexInput?.value, 10);
    return Number.isFinite(v) && v > 0 ? v : 1;
}

function getDelimiter() {
    const val = delimiterInput ? delimiterInput.value : ',';
    return val === ',' ? null : val;
}

function resetSheetState() {
    availableSheets = [];
    selectedSheet = null;
    if (sheetSelect) sheetSelect.innerHTML = '<option value="">— Select a sheet —</option>';
    if (sheetSelectorRow) sheetSelectorRow.style.display = 'none';
    if (sheetStatus) sheetStatus.textContent = '';
}

// ============================================================
// SUPPLIER UNIQUENESS
// ============================================================
async function fetchAllSuppliers() {
    try {
        const response = await fetch('/api/mappings-list');
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

// ============================================================
// FETCH SHEETS (Excel only)
// ============================================================
async function fetchSheets() {
    if (!sampleFileInput.files.length) {
        if (sheetStatus) sheetStatus.innerHTML = '<span class="text-warning">⚠️ Select an Excel file first</span>';
        return;
    }

    const file = sampleFileInput.files[0];
    if (!isExcelFile(file)) {
        if (sheetStatus) sheetStatus.innerHTML = '<span class="text-warning">⚠️ Sheet selection is only for Excel files</span>';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    if (sheetStatus) sheetStatus.innerHTML = '<span class="text-info">⏳ Fetching sheets...</span>';
    if (fetchSheetsBtn) fetchSheetsBtn.disabled = true;

    try {
        const response = await fetch('/api/parse-sheets', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        availableSheets = data.available_sheets || [];
        uploadedFilePath = data.file_path || null;

        sheetSelect.innerHTML = '';
        availableSheets.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            sheetSelect.appendChild(opt);
        });

        if (availableSheets.length > 0) {
            sheetSelect.value = availableSheets[0];
            selectedSheet = availableSheets[0];
            if (sheetStatus) sheetStatus.innerHTML =
                `<span class="text-success">✅ ${availableSheets.length} sheet(s) found</span>`;
        } else {
            selectedSheet = null;
            if (sheetStatus) sheetStatus.innerHTML =
                '<span class="text-warning">⚠️ No sheets found</span>';
        }

        sheetSelectorRow.style.display = 'block';
    } catch (e) {
        console.error('fetchSheets failed:', e);
        if (sheetStatus) sheetStatus.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', `Failed to fetch sheets: ${e.message}`, 'danger');
    } finally {
        if (fetchSheetsBtn) fetchSheetsBtn.disabled = false;
        updateStepStates();
    }
}

// ============================================================
// FILE CHANGE HANDLER
// ============================================================
async function handleFileChange() {
    const fileInput = sampleFileInput;
    const file = fileInput.files[0];

    resetSheetState();
    uploadedFilePath = null;

    // ✅ Reset parse-time config on file change (window-scoped)
    window.parsedHeaderRowIndex = null;
    window.parsedSheetName = null;
    window.parsedDelimiter = null;

    if (!file) {
        if (fileTypeHint) fileTypeHint.textContent = '';
        if (delimiterRow) delimiterRow.style.display = 'none';
        updateStepStates();
        return;
    }

    if (isCsvFile(file)) {
        if (fileTypeHint) fileTypeHint.textContent = 'CSV file detected — no sheet selection needed.';
        if (delimiterRow) delimiterRow.style.display = 'flex';
        if (sheetSelectorRow) sheetSelectorRow.style.display = 'none';
    } else if (isExcelFile(file)) {
        if (fileTypeHint) fileTypeHint.textContent = 'Excel file detected — fetching sheets...';
        if (delimiterRow) delimiterRow.style.display = 'none';
        await fetchSheets();
    } else {
        if (fileTypeHint) fileTypeHint.innerHTML =
            '<span class="text-danger">Unsupported file type. Use CSV or Excel.</span>';
        if (delimiterRow) delimiterRow.style.display = 'none';
    }

    updateStepStates();
}

// ============================================================
// PARSE SAMPLE FILE
// ============================================================
async function parseSampleFile() {
    const statusDiv = document.getElementById('parseStatus');
    const previewDiv = document.getElementById('filePreview');
    const file = sampleFileInput.files[0];

    if (!file) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Please select a file</span>';
        return;
    }

    const supplierName = supplierNameInput.value.trim();
    if (!supplierName) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Enter a supplier name first</span>';
        return;
    }

    const headerRow = getHeaderRowIndex();
    const delim = getDelimiter();

    const formData = new FormData();
    formData.append('file', file);
    formData.append('supplier_name', supplierName);
    formData.append('header_row_index', String(headerRow));

    if (isExcelFile(file) && selectedSheet) {
        formData.append('sheet_name', selectedSheet);
    }

    if (isCsvFile(file)) {
        formData.append('delimiter', delim === null ? ',' : delim);
    }

    statusDiv.innerHTML = '<span class="text-info">⏳ Uploading & parsing...</span>';
    parseFileBtn.disabled = true;

    console.log('[add_supplier] Parsing sample file with data:', {
        supplier_name: supplierName,
        header_row_index: headerRow,
        sheet_name: selectedSheet,
        delimiter: delim,
    });

    try {
        const response = await fetch('/api/parse-sample', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        parsedColumns = data.columns || [];
        parsedFileColumns = parsedColumns;
        const preview = data.preview || [];

        // ✅ Persist parse-time config (window-scoped for cross-file access)
        window.parsedHeaderRowIndex = headerRow;
        window.parsedSheetName = selectedSheet || null;
        window.parsedDelimiter = (delim === null ? ',' : delim);

        console.log('[add_supplier] ✅ Parse succeeded. Stored config:', {
            parsedHeaderRowIndex: window.parsedHeaderRowIndex,
            parsedSheetName: window.parsedSheetName,
            parsedDelimiter: window.parsedDelimiter,
        });

        previewDiv.style.display = 'block';
        renderPreview(preview);

        step2Complete = true;
        buildMappingUI(targetColumns, parsedColumns);

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

function renderPreview(preview) {
    const head = document.getElementById('previewHead');
    const body = document.getElementById('previewBody');

    if (!preview.length) {
        head.innerHTML = '';
        body.innerHTML = '<tr><td colspan="10" class="text-muted">No preview data</td></tr>';
        return;
    }

    const headers = Object.keys(preview[0]);
    head.innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;

    const rows = preview.slice(0, 5);
    body.innerHTML = rows.map(row =>
        `<tr>${headers.map(h => `<td>${row[h] || ''}</td>`).join('')}</tr>`
    ).join('');
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
// BUILD MAPPING UI
// ============================================================
function buildMappingUI(targetCols, fileCols) {
    const tbody = document.getElementById('mappingTableBody');

    parsedFileColumns = fileCols || [];
    mappingArea.style.display = 'block';
    noFileMessage.style.display = 'none';

    currentMappings = {};
    initialMappings = {};
    prepopulatedValues = {};

    const sorted = [...targetCols].sort((a, b) => {
        const aR = a.nullable === false;
        const bR = b.nullable === false;
        if (aR && !bR) return -1;
        if (!aR && bR) return 1;
        return 0;
    });

    let html = '';
    sorted.forEach((col, index) => {
        const isMandatory = col.nullable === false;
        const fieldId = col.target_field_id;
        const fieldName = col.name || col.field_name || 'Unknown';
        const rowId = `row-${index}`;

        const init = {
            target: fieldName,
            source: null,
            prepopulated: false,
            prepopulated_value: null,
            target_id: fieldId,
            is_mandatory: isMandatory,
        };
        currentMappings[fieldId] = { ...init };
        initialMappings[fieldId] = { ...init };

        html += `<tr id="${rowId}">
            <td>${index + 1}</td>
            <td>
                <strong>${fieldName}</strong>
                ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                <br><span class="text-muted small">${col.type || ''}</span>
                <br><span class="text-muted small">ID: ${fieldId}</span>
            </td>
            <td>
                <select class="form-select form-select-sm source-select"
                        data-target-id="${fieldId}"
                        data-target-name="${fieldName}"
                        data-type="${col.type || ''}">
                    <option value="None">None</option>
                    ${fileCols.map(fc => `<option value="${fc}">${fc}</option>`).join('')}
                </select>
            </td>
            <td class="text-center">
                <input type="checkbox" class="form-check-input mandatory-check"
                       data-target-id="${fieldId}"
                       ${isMandatory ? 'checked disabled' : ''}>
            </td>
            <td>
                <input type="text" class="form-control form-control-sm prepopulated-value"
                       data-target-id="${fieldId}"
                       placeholder="Pre Populated value...">
            </td>
        </tr>`;
    });

    tbody.innerHTML = html;
    step2Complete = true;

    document.querySelectorAll('.source-select').forEach(el => {
        el.removeEventListener('change', handleSourceChange);
        el.addEventListener('change', handleSourceChange);
    });
    document.querySelectorAll('.mandatory-check').forEach(el => {
        el.removeEventListener('change', handleMandatoryChange);
        el.addEventListener('change', handleMandatoryChange);
    });
    document.querySelectorAll('.prepopulated-value').forEach(el => {
        el.removeEventListener('input', handlePrepopulatedInput);
        el.addEventListener('input', handlePrepopulatedInput);
    });

    window._mappingTargets = sorted.reduce((acc, col) => {
        acc[col.target_field_id] = col.name || col.field_name || 'Unknown';
        return acc;
    }, {});
    window.targetColumns = targetCols;

    updateMappingStatus();
    updateStepStates();
}

// ============================================================
// EVENT HANDLERS
// ============================================================
function handleSourceChange() {
    const targetId = parseInt(this.dataset.targetId, 10);
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

    // ✅ Reset parse-time config (window-scoped)
    window.parsedHeaderRowIndex = null;
    window.parsedSheetName = null;
    window.parsedDelimiter = null;
    uploadedFilePath = null;

    if (delimiterInput) delimiterInput.value = ',';
    if (delimiterRow) delimiterRow.style.display = 'none';
    if (headerRowIndexInput) headerRowIndexInput.value = '1';

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
    if (sampleFileInput) {
        sampleFileInput.addEventListener('change', handleFileChange);
    }
    if (sheetSelect) {
        sheetSelect.addEventListener('change', function () {
            selectedSheet = this.value || null;
            updateStepStates();
        });
    }

    updateStepStates();
});