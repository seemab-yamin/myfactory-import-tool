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
        const prepopulatedInput = document.querySelector(`${prepopulatedSelector}[data-target-id="${targetId}"]`);

        currentState[targetName] = {
            target_id: targetId,
            source_field: sourceField,
            is_mandatory: mandatoryCheck ? mandatoryCheck.checked : false,
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
    const saveBtn = document.getElementById('saveBtn');
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
// SAVE MAPPINGS – WITH TARGET NAME + EDITABLE CONFIG + TRACE LOGS
// ============================================================

async function saveMappings() {
    const TAG = '[saveMappings]';
    console.log(`${TAG} ▶ START`);

    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('saveStatus');

    // ============================================================
    // Step 1: Get supplier name
    // ============================================================
    let supplierName = '';

    const data = getPageData();
    if (data?.supplierName) {
        supplierName = data.supplierName;
        console.log(`${TAG} [1] supplierName from getPageData():`, supplierName);
    } else {
        const nameInput = document.getElementById('supplierName');
        if (nameInput) {
            supplierName = nameInput.value.trim();
            console.log(`${TAG} [1] supplierName from #supplierName input:`, supplierName);
        }
    }

    if (!supplierName) {
        const titleEl = document.getElementById('detailTitle');
        if (titleEl) {
            supplierName = titleEl.textContent?.trim() || '';
            console.log(`${TAG} [1] supplierName from #detailTitle:`, supplierName);
        }
    }

    if (!supplierName) {
        console.error(`${TAG} [1] ❌ supplierName not found — aborting`);
        statusDiv.innerHTML = '<span class="text-danger">❌ Supplier name not found. Please enter a name.</span>';
        showToast('Error', 'Supplier name not found', 'danger');
        return;
    }

    // ============================================================
    // Step 2: Get page data
    // ============================================================
    const pageData = getPageData();
    console.log(`${TAG} [2] pageData:`, pageData);

    // ============================================================
    // Step 3: Determine source fields
    // ============================================================
    let sourceFields = [];

    if (pageData?.sourceFields && pageData.sourceFields.length > 0) {
        sourceFields = pageData.sourceFields;
        console.log(`${TAG} [3] sourceFields from pageData (backend):`, sourceFields.length);
    } else if (parsedFileColumns && parsedFileColumns.length > 0) {
        sourceFields = parsedFileColumns;
        console.log(`${TAG} [3] sourceFields from parsedFileColumns:`, sourceFields.length);
    } else {
        const sourceFieldsEl = document.getElementById('page-data');
        if (sourceFieldsEl) {
            try {
                const sourceData = JSON.parse(sourceFieldsEl.dataset.sourceFields || '[]');
                if (sourceData.length > 0) {
                    sourceFields = sourceData;
                    console.log(`${TAG} [3] sourceFields from #page-data fallback:`, sourceFields.length);
                }
            } catch (e) {
                console.warn(`${TAG} [3] Could not parse source_fields from data attribute:`, e);
            }
        }
    }
    console.log(`${TAG} [3] Final sourceFields:`, sourceFields);

    // ============================================================
    // Step 3b: Read editable config fields (TRACE FOCUS)
    // ============================================================
    // Fallback chain per field:
    //   input element  →  pageData (edit page)  →  window.parsed* (create page)  →  default
    console.log(`${TAG} [3b] ─── CONFIG FIELD TRACE BEGIN ───`);

    const sheetNameInput = document.getElementById('sheetNameInput');
    const headerRowInput = document.getElementById('headerRowInput');
    const delimiterInput = document.getElementById('delimiterInput');

    console.log(`${TAG} [3b] sheetNameInput element:`, sheetNameInput);
    console.log(`${TAG} [3b] headerRowInput element:`, headerRowInput);
    console.log(`${TAG} [3b] delimiterInput element:`, delimiterInput);
    console.log(`${TAG} [3b] window.parsed*:`, {
        parsedHeaderRowIndex: window.parsedHeaderRowIndex,
        parsedSheetName: window.parsedSheetName,
        parsedDelimiter: window.parsedDelimiter,
    });

    // ── sheet_name ──
    const sheetName = sheetNameInput
        ? (sheetNameInput.value.trim() || null)
        : (pageData?.sheetName ?? window.parsedSheetName ?? null);

    console.log(`${TAG} [3b] sheetName:`,
        'input=', sheetNameInput?.value,
        '| pageData=', pageData?.sheetName,
        '| window.parsed=', window.parsedSheetName,
        '| resolved=', sheetName);

    // ── header_row_index ──
    const headerRowRaw = headerRowInput
        ? headerRowInput.value.trim()
        : (pageData?.headerRowIndex ?? window.parsedHeaderRowIndex ?? '');

    console.log(`${TAG} [3b] headerRowRaw:`,
        'input=', headerRowInput?.value,
        '| pageData=', pageData?.headerRowIndex,
        '| window.parsed=', window.parsedHeaderRowIndex,
        '| raw=', JSON.stringify(headerRowRaw));

    const headerRowIndex = headerRowRaw !== '' && headerRowRaw != null
        ? Number.parseInt(headerRowRaw, 10)
        : 1;
    console.log(`${TAG} [3b] headerRowIndex parsed:`,
        headerRowIndex, '| typeof:', typeof headerRowIndex);

    // ── delimiter ──
    const delimiter = delimiterInput
        ? (delimiterInput.value.trim() || ',')
        : (pageData?.delimiter ?? window.parsedDelimiter ?? ',');

    console.log(`${TAG} [3b] delimiter:`,
        'input=', delimiterInput?.value,
        '| pageData=', pageData?.delimiter,
        '| window.parsed=', window.parsedDelimiter,
        '| resolved=', delimiter);

    console.log(`${TAG} [3b] ─── CONFIG FIELD TRACE END ───`);

    // ============================================================
    // Step 4: Collect current state from UI
    // ============================================================
    const currentState = collectMappingsFromUI();
    console.log(`${TAG} [4] currentState keys:`, Object.keys(currentState).length);

    // ============================================================
    // Step 5: Ensure initialMappings exists
    // ============================================================
    if (!initialMappings || Object.keys(initialMappings).length === 0) {
        initialMappings = JSON.parse(JSON.stringify(currentState));
        console.log(`${TAG} [5] initialMappings seeded from currentState`);
    } else {
        console.log(`${TAG} [5] initialMappings already exists:`,
            Object.keys(initialMappings).length, 'keys');
    }

    // ============================================================
    // Step 6: Detect changes
    // ============================================================
    const changes = detectChanges(currentState, initialMappings);
    console.log(`${TAG} [6] mapping changes detected:`, changes.length);

    const configChanged =
        (sheetName || null) !== (pageData?.sheetName || null) ||
        (Number.isInteger(headerRowIndex) ? headerRowIndex : null) !== (pageData?.headerRowIndex ?? null) ||
        (delimiter || ',') !== (pageData?.delimiter || ',');

    console.log(`${TAG} [6] configChanged:`, configChanged, {
        sheetName: { current: sheetName, original: pageData?.sheetName },
        headerRowIndex: { current: headerRowIndex, original: pageData?.headerRowIndex },
        delimiter: { current: delimiter, original: pageData?.delimiter },
    });

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
    console.log(`${TAG} [7] mandatory errors:`, mandatoryErrors.length);
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
        prepopulated_value: state.prepopulated_value || ''
    }));
    console.log(`${TAG} [8] mappingList length:`, mappingList.length);

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
    console.log(`${TAG} [9] isNewSupplierPage:`, isNew);

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

    console.log(`${TAG} [10] ─── FINAL PAYLOAD ───`);
    console.log(`${TAG} [10] sheet_name:`, payload.sheet_name, `(typeof: ${typeof payload.sheet_name})`);
    console.log(`${TAG} [10] header_row_index:`, payload.header_row_index, `(typeof: ${typeof payload.header_row_index})`);
    console.log(`${TAG} [10] delimiter:`, payload.delimiter, `(typeof: ${typeof payload.delimiter})`);
    console.log(`${TAG} [10] Full payload JSON:`, JSON.stringify(payload, null, 2));

    // ============================================================
    // Step 11: Send to backend
    // ============================================================
    const url = `/api/mappings/${encodeURIComponent(supplierName)}`;
    console.log(`${TAG} [11] POST →`, url);

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

        console.log(`${TAG} [11] Response status:`, response.status, response.statusText);

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
        console.log(`${TAG} [11] ✅ Save success. Response:`, result);
        console.log(`${TAG} [11] ⚠️ Console will clear after redirect in 1.5s — capture logs now.`);

        hasChanges = false;
        updateSaveButton();

        statusDiv.innerHTML = `<span class="text-success">✅ ${mappingList.length} mappings saved successfully!</span>`;
        showToast('Success', `Mappings saved for ${supplierName}`, 'success');
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Changes';

        setTimeout(() => {
            const redirectUrl = result.supplier_id
                ? `/show-mapping/${result.supplier_id}`
                : window.location.href;
            console.log(`${TAG} [11] Redirecting →`, redirectUrl);
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
        if (state.is_mandatory) {
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