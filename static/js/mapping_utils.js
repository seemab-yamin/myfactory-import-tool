let targetColumns = [];
let supplierExists = false;
// ===== Step Unlock State =====
let step1Complete = false;
let step2Complete = false;

// Sheet fetch state
let availableSheets = [];
let selectedSheet = null;
let uploadedFilePath = null;
let initialMappings = {};

// ===== DOM References =====
const fetchSheetsBtn = document.getElementById('fetchSheetsBtn');
const sheetSelect = document.getElementById('sheetSelect');
const delimiterInput = document.getElementById('delimiterInput');
const delimiterChar = document.getElementById('delimiterChar');
const saveBtn = document.getElementById('saveBtn');
const parseFileBtn = document.getElementById('parseFileBtn');
const noFileMessage = document.getElementById('noFileMessage');
const mappingArea = document.getElementById('mappingArea');
const autoMapBtn = document.getElementById('autoMapBtn');
const sheetStatus = document.getElementById('sheetStatus');
const sampleFileInput = document.getElementById('sampleFile');
const supplierNameInput = document.getElementById('supplierName');
const autoMapStatus = document.getElementById('autoMapStatus');
const fileTypeHint = document.getElementById('fileTypeHint');
const headerRowIndexInput = document.getElementById('headerRowIndex');

const delimiterRow = document.getElementById('delimiterRow');
const sheetSelectorRow = document.getElementById('sheetSelectorRow');

/**
 * mapping_utils.js – Shared utility functions for mapping UI
 * Used by both add_mapping.js and show_mapping.js
 */

// ============================================================
// GET PAGE DATA (from show_mapping.html)
// ============================================================

function getPageData() {
    const el = document.getElementById('page-data');
    if (!el) return null;

    try {
        let supplierMappings = JSON.parse(el.dataset.supplierMappings || '[]');
        if (!Array.isArray(supplierMappings)) {
            supplierMappings = Object.values(supplierMappings);
        }

        return {
            supplierId: parseInt(el.dataset.supplierId),
            supplierName: el.dataset.supplierName,
            sourceFields: JSON.parse(el.dataset.sourceFields || '[]'),
            supplierMappings: supplierMappings
        };
    } catch (e) {
        console.error('❌ Failed to parse page data:', e);
        return null;
    }
}

// ============================================================
// HELPERS
// ============================================================
function resetSheetState() {
    availableSheets = [];
    selectedSheet = null;
    if (sheetSelect) sheetSelect.innerHTML = '<option value="">— Select a sheet —</option>';
    if (sheetSelectorRow) sheetSelectorRow.style.display = 'none';
    if (sheetStatus) sheetStatus.textContent = '';
}
function getDelimiter() {
    const val = delimiterChar ? delimiterChar.value : delimiterInput ? delimiterInput.value : ',';
    return val === ',' ? null : val;
}

function isCsvFile(file) {
    if (!file) return false;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    return ext === 'csv';
}

function isExcelFile(file) {
    if (!file) return false;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    return ext === 'xlsx' || ext === 'xls';
}

function getHeaderRowIndex() {
    const v = parseInt(headerRowIndexInput?.value, 10);
    return Number.isFinite(v) && v > 0 ? v : 1;
}

function clearAutoMapVisuals() {
    document.querySelectorAll('.source-select').forEach(sel => {
        sel.classList.remove('auto-mapped-exact', 'auto-mapped-fuzzy');
        sel.removeAttribute('title');
    });
    document.querySelectorAll('.fuzzy-warning').forEach(el => el.remove());
}

// ============================================================
// 1. COLLECT MAPPINGS FROM UI
// ============================================================

/**
 * Collects current mapping state from the UI (dropdowns, checkboxes, inputs)
 */
function collectMappingsFromUI(
    selectSelector = '.source-select',
    mandatorySelector = '.mandatory-check',
    prepopulatedSelector = '.prepopulated-value'
) {
    const selects = document.querySelectorAll(selectSelector);
    const currentState = {};

    selects.forEach(select => {
        const targetName = select.dataset.targetName;
        const targetId = parseInt(select.dataset.targetId);
        const sourceField = select.value === '' || select.value === 'None' ? null : select.value;
        const mandatoryCheck = document.querySelector(`${mandatorySelector}[data-target-id="${targetId}"]`);
        const isDbRequired = select.dataset.dbRequired;
        const prepopulatedInput = document.querySelector(`${prepopulatedSelector}[data-target-id="${targetId}"]`);
        currentState[targetName] = {
            target_id: targetId,
            source_field: sourceField,
            is_mandatory: mandatoryCheck ? mandatoryCheck.checked : false,
            is_db_required: isDbRequired === true || isDbRequired === "true",
            prepopulated_value: prepopulatedInput ? prepopulatedInput.value.trim() : '',
            data_type: select.dataset.type || ''
        };
    });

    return currentState;
}

// ============================================================
// UI HELPERS
// ============================================================

function updateSaveButton() {
    if (saveBtn) saveBtn.disabled = !hasChanges;
}

// ============================================================
// 3. DETECT CHANGES
// ============================================================

function detectChanges(currentState, initialState) {
    const changes = [];

    const allTargets = new Set([
        ...Object.keys(currentState),
        ...Object.keys(initialState)
    ]);

    for (const targetName of allTargets) {
        const cur = currentState[targetName] || { source_field: null, is_mandatory: false, prepopulated_value: '' };
        const init = initialState[targetName] || { source_field: null, is_mandatory: false, prepopulated_value: '' };

        const sourceChanged = cur.source_field !== init.source_field;
        const mandatoryChanged = cur.is_mandatory !== init.is_mandatory;
        const prepopulatedChanged = cur.prepopulated_value !== init.prepopulated_value;

        if (sourceChanged || mandatoryChanged || prepopulatedChanged) {
            const was_removed = init.source_field !== null &&
                (cur.source_field === null || cur.source_field === '') &&
                (!cur.prepopulated_value || cur.prepopulated_value.trim() === '') &&
                !init.is_mandatory;

            changes.push({
                target_name: targetName,
                target_id: cur.target_id || 0,
                source_field: cur.source_field,
                is_mandatory: cur.is_mandatory,
                prepopulated_value: cur.prepopulated_value || '',
                was_removed: was_removed,
                _initial_source: init.source_field,
                _initial_mandatory: init.is_mandatory,
                _initial_prepopulated: init.prepopulated_value
            });
        }
    }

    return changes;
}

// ============================================================
// 6. HIGHLIGHT ERROR ROWS
// ============================================================

function highlightErrorRows(errors) {
    document.querySelectorAll('.table-danger').forEach(el => el.classList.remove('table-danger'));

    errors.forEach(err => {
        const row = document.querySelector(`tr:has(.source-select[data-target-name="${err.target_name}"])`);
        if (row) {
            row.classList.add('table-danger');
        }
    });
}

// ============================================================
// 7. SCROLL TO FIRST ERROR
// ============================================================

function scrollToFirstError() {
    const firstErrorRow = document.querySelector('.table-danger');
    if (firstErrorRow) {
        firstErrorRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// ============================================================
// 8. SHOW VALIDATION ERRORS IN UI
// ============================================================

function renderValidationErrors(statusDiv, errors) {
    if (!statusDiv) return;

    let html = `<div class="text-danger"><strong>❌ ${errors.length} validation error(s):</strong></div>`;
    html += `<ul class="mb-0">`;
    errors.forEach(err => {
        html += `<li><strong>${err.target_name}</strong>: ${err.message}</li>`;
    });
    html += `</ul>`;
    html += `<div class="mt-2"><small>Please fix the highlighted fields and try again.</small></div>`;
    statusDiv.innerHTML = html;
}

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

function updateStepIndicators() {
    document.querySelectorAll('[data-step]').forEach(card => {
        const step = parseInt(card.dataset.step);
        card.classList.toggle('active', step === getCurrentStep());
        card.classList.toggle('completed', step < getCurrentStep());
    });

    updateStepStatus(1, step1Complete, 'Enter supplier name', 'Name already exists');
    updateStepStatus(2, step2Complete, 'Upload a file', '');
}

// ============================================================
// FILE CHANGE HANDLER
// ============================================================
async function handleFileChange() {
    const fileInput = sampleFileInput;
    const file = fileInput.files[0];

    resetSheetState();
    uploadedFilePath = null;

    window.parsedHeaderRowIndex = null;
    window.parsedSheetName = null;
    window.parsedDelimiter = null;

    // Reset auto-map UI
    if (autoMapBtn) autoMapBtn.disabled = true;
    if (autoMapStatus) autoMapStatus.innerHTML = '';
    clearAutoMapVisuals();

    // ✅ Hide the summary banner
    const banner = document.getElementById('autoMapSummary');
    if (banner) banner.classList.add('d-none');

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
// BUILD MAPPING UI
// ============================================================
function buildMappingUI(targetCols, fileCols) {
    const tbody = document.getElementById('mappingTableBody');
    console.log(`Building mapping UI with ${targetCols.length} target columns and ${fileCols.length} source columns`);
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
        const isDbRequired = col.nullable === false;
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
            is_db_required: isDbRequired
        };
        currentMappings[fieldId] = { ...init };
        initialMappings[fieldId] = { ...init };

        html += `<tr id="${rowId}">
            <td>${index + 1}</td>
            <td>
                <strong>${fieldName}</strong>
                ${isDbRequired ? '<span class="text-danger">*</span>' : ''}
                <br><span class="text-muted small">${col.type || ''}</span>
                <br><span class="text-muted small">ID: ${fieldId}</span>
            </td>
            <td>
                <select class="form-select form-select-sm source-select" data-target-id="${fieldId}" data-target-name="${fieldName}" data-type="${col.type || ''}" data-db-required="${isDbRequired}">
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

/**
 * Pure parse-only function.
 * Sends a file to /api/parse-sample and returns the parsed result.
 * Throws on network or server error. No DOM access, no UI side effects.
 *
 * @param {File}        file       - File to parse
 * @param {number}      headerRow  - Header row index (1-based)
 * @param {string|null} delim      - Delimiter for CSV (null = let backend sniff)
 * @param {string|null} sheetName  - Excel sheet name (null = first sheet)
 * @returns {Promise<Object>} Parsed result: { columns, preview, ... }
 */
async function parseFileOnly(file, headerRow, delim, sheetName) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('header_row_index', String(headerRow));

    if (isExcelFile(file) && sheetName) {
        formData.append('sheet_name', sheetName);
    }

    if (isCsvFile(file)) {
        formData.append('delimiter', delim === null ? ',' : delim);
    }

    const response = await fetch('/api/parse-sample', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Applies parsed data to the UI: stores config, renders preview,
 * updates global state. Caller is responsible for error handling.
 *
 * @param {Object}      data       - Response from parseFileOnly
 * @param {number}      headerRow  - Header row index used
 * @param {string|null} delim      - Delimiter used
 * @param {string|null} sheetName  - Sheet name used
 */
async function parseRender() {
    const headerRow = getHeaderRowIndex();
    const delim = getDelimiter();
    const sheetName = selectedSheet || null;

    const file = sampleFileInput.files[0];

    // ✅ Validation (UI concern) — bail early before touching network
    if (!file) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Please select a file</span>';
        return;
    }

    // 1. Pure API call
    const data = await parseFileOnly(file, headerRow, delim, sheetName);
    const previewDiv = document.getElementById('filePreview');

    parsedColumns = data.columns || [];
    parsedFileColumns = parsedColumns;
    const preview = data.preview || [];

    // ✅ UI state (cross-page, consumed by saveMappings)
    window.parsedHeaderRowIndex = headerRow;
    window.parsedSheetName = sheetName;
    window.parsedDelimiter = (delim === null ? ',' : delim);

    if (previewDiv) previewDiv.style.display = 'block';
    renderPreview(preview);

    step2Complete = true;
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
// Step 1: Get supplier name
// ============================================================
function getSupplierName() {
    let supplierName = '';

    const data = getPageData();
    if (data?.supplierName) {
        supplierName = data.supplierName;
    } else {
        const nameInput = document.getElementById('supplierName');
        if (nameInput) {
            supplierName = nameInput.value.trim();
        }
    }

    if (!supplierName) {
        const titleEl = document.getElementById('detailTitle');
        if (titleEl) {
            supplierName = titleEl.textContent?.trim() || '';
        }
    }

    if (!supplierName) {
        console.error(`${TAG} [1] ❌ supplierName not found — aborting`);
        statusDiv.innerHTML = '<span class="text-danger">❌ Supplier name not found. Please enter a name.</span>';
        showToast('Error', 'Supplier name not found', 'danger');
        return;
    }
    return supplierName;
}

// ============================================================
// SAVE MAPPINGS – WITH TARGET NAME + EDITABLE CONFIG + TRACE LOGS
// ============================================================

async function saveMappings() {
    const TAG = '[saveMappings]';
    const statusDiv = document.getElementById('saveStatus');
    const supplierName = getSupplierName();

    // ============================================================
    // Step 2: Get page data
    // ============================================================
    const pageData = getPageData();
    // ============================================================
    // Step 3: Determine source fields
    // ============================================================
    let sourceFields = [];

    if (pageData?.sourceFields && pageData.sourceFields.length > 0) {
        sourceFields = pageData.sourceFields;
    } else if (parsedFileColumns && parsedFileColumns.length > 0) {
        sourceFields = parsedFileColumns;
    } else {
        const sourceFieldsEl = document.getElementById('page-data');
        if (sourceFieldsEl) {
            try {
                const sourceData = JSON.parse(sourceFieldsEl.dataset.sourceFields || '[]');
                if (sourceData.length > 0) {
                    sourceFields = sourceData;
                }
            } catch (e) {
                console.warn(`${TAG} [3] Could not parse source_fields from data attribute:`, e);
            }
        }
    }

    // ============================================================
    // Step 3b: Read editable config fields (TRACE FOCUS)
    // ============================================================
    // Fallback chain per field:
    //   input element  →  pageData (edit page)  →  window.parsed* (create page)  →  default

    const sheetNameInput = document.getElementById('sheetNameInput');
    const headerRowInput = document.getElementById('headerRowInput');
    const delimiterInput = document.getElementById('delimiterInput');

    // ── sheet_name ──
    const sheetName = sheetNameInput
        ? (sheetNameInput.value.trim() || null)
        : (pageData?.sheetName ?? window.parsedSheetName ?? null);


    // ── header_row_index ──
    const headerRowRaw = headerRowInput
        ? headerRowInput.value.trim()
        : (pageData?.headerRowIndex ?? window.parsedHeaderRowIndex ?? '');

    const headerRowIndex = headerRowRaw !== '' && headerRowRaw != null
        ? Number.parseInt(headerRowRaw, 10)
        : 1;

    // ── delimiter ──
    const delimiter = delimiterInput
        ? (delimiterInput.value.trim() || ',')
        : (pageData?.delimiter ?? window.parsedDelimiter ?? ',');

    // ============================================================
    // Step 4: Collect current state from UI
    // ============================================================
    const currentState = collectMappingsFromUI();

    // ============================================================
    // Step 5: Ensure initialMappings exists
    // ============================================================
    if (!initialMappings || Object.keys(initialMappings).length === 0) {
        initialMappings = JSON.parse(JSON.stringify(currentState));
    }

    // ============================================================
    // Step 6: Detect changes
    // ============================================================
    const changes = detectChanges(currentState, initialMappings);

    const configChanged =
        (sheetName || null) !== (pageData?.sheetName || null) ||
        (Number.isInteger(headerRowIndex) ? headerRowIndex : null) !== (pageData?.headerRowIndex ?? null) ||
        (delimiter || ',') !== (pageData?.delimiter || ',');


    if (changes.length === 0 && !configChanged) {
        console.warn(`${TAG} [6] ⚠️ No changes — aborting save`);
        statusDiv.innerHTML = '<span class="text-info">ℹ️ No changes to save.</span>';
        showToast('Info', 'No changes to save', 'info');
        return;
    }

    // ============================================================
    // Step 7: Validate mandatory fields
    // ============================================================
    const mandatoryErrors = validateMandatoryFields(currentState);
    if (mandatoryErrors.length > 0) {
        console.error(`${TAG} [7] ❌ Mandatory validation failed:`, mandatoryErrors);
        highlightErrorRows(mandatoryErrors);
        renderValidationErrors(statusDiv, mandatoryErrors);
        showToast('Validation Error', `${mandatoryErrors.length} mandatory field(s) missing values.`, 'danger');
        scrollToFirstError();
        return;
    }

    // ============================================================
    // Step 8: Build COMPLETE mapping list (ALL fields)
    // ============================================================
    const mappingList = Object.entries(currentState).map(([targetName, state]) => ({
        target_field_name: targetName,
        source_field: state.source_field || '',
        target_field_id: state.target_id,
        data_type: state.data_type || '',
        is_active: true,
        is_mandatory: state.is_mandatory || false,
        is_db_required: state.is_db_required || false,
        prepopulated_value: state.prepopulated_value || ''
    }));

    if (mappingList.length === 0) {
        console.warn(`${TAG} [8] ⚠️ Empty mappingList — aborting`);
        statusDiv.innerHTML = '<span class="text-warning">⚠️ No valid mappings to save.</span>';
        showToast('Warning', 'No valid mappings to save.', 'warning');
        return;
    }

    // ============================================================
    // Step 9: Detect if this is a new supplier
    // ============================================================
    function isNewSupplierPage() {
        const pageDataEl = document.getElementById('page-data');
        if (pageDataEl && pageDataEl.dataset.supplierId) {
            return false;
        }
        if (document.getElementById('supplierName')) {
            return true;
        }
        if (window.location.pathname.includes('/add-mapping')) {
            return true;
        }
        return true;
    }

    const isNew = isNewSupplierPage();
    // TODO
    // ============================================================
    // Step 10: Build payload
    // ============================================================
    const payload = {
        source_fields: sourceFields,
        mappings: mappingList,
        is_new_supplier: isNew,
        sheet_name: sheetName,
        header_row_index: Number.isInteger(headerRowIndex) ? headerRowIndex : 1,
        delimiter: delimiter,
    };

    // ============================================================
    // Step 11: Send to backend
    // ============================================================
    const url = `/api/suppliers/${encodeURIComponent(supplierName)}`;

    saveBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-info">⏳ Saving ${mappingList.length} mapping(s)...</span>`;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });


        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            let errorDetail = null;

            try {
                const errorData = await response.json();
                console.error(`${TAG} [11] ❌ Backend error response:`, errorData);
                errorDetail = errorData;
                errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
            } catch (e) {
                errorMessage = response.statusText || errorMessage;
            }

            throw { message: errorMessage, detail: errorDetail, status: response.status };
        }

        const result = await response.json();

        hasChanges = false;
        updateSaveButton();

        statusDiv.innerHTML = `<span class="text-success">✅ ${mappingList.length} mappings saved successfully!</span>`;
        showToast('Success', `Mappings saved for ${supplierName}`, 'success');
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Changes';

        setTimeout(() => {
            const redirectUrl = result.supplier_id
                ? `/show-mapping/${result.supplier_id}`
                : window.location.href;
            if (result.supplier_id) {
                window.location.href = redirectUrl;
            } else {
                window.location.reload();
            }
        }, 1500);

    } catch (error) {
        console.error(`${TAG} [11] ❌ Save failed:`, error);

        const errorMsg = error.detail ? JSON.stringify(error.detail) : error.message;
        statusDiv.innerHTML = `<span class="text-danger">❌ ${errorMsg}</span>`;
        showToast('Error', `Failed to save mappings: ${error.message}`, 'danger');
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Changes';
    }
}

/**
 * Validates mandatory fields in the current state.
 */
function validateMandatoryFields(currentState) {
    const errors = [];
    for (const [targetName, state] of Object.entries(currentState)) {
        if (state.is_mandatory || state.is_db_required) {
            const hasSource = state.source_field && state.source_field.trim() !== '';
            const hasPrepop = state.prepopulated_value && state.prepopulated_value.trim() !== '';
            if (!hasSource && !hasPrepop) {
                errors.push({
                    target_name: targetName,
                    message: 'Mandatory field requires either a source field or a prepopulated value.'
                });
            }
        }
    }
    return errors;
}

// Make it globally accessible
window.validateMandatoryFields = validateMandatoryFields;

// ============================================================
// 10. EXPOSE TO GLOBAL SCOPE (for use in other scripts)
// ============================================================

window.collectMappingsFromUI = collectMappingsFromUI;
window.detectChanges = detectChanges;
window.highlightErrorRows = highlightErrorRows;
window.scrollToFirstError = scrollToFirstError;
window.renderValidationErrors = renderValidationErrors;



// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', async function () {
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