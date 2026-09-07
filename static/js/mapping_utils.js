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
 * @param {string} selectSelector - CSS selector for source selects (default: '.source-select')
 * @param {string} mandatorySelector - CSS selector for mandatory checkboxes (default: '.mandatory-check')
 * @param {string} prepopulatedSelector - CSS selector for prepopulated inputs (default: '.prepopulated-value')
 * @returns {Object} currentState - { targetName: { target_id, source_field, is_mandatory, prepopulated_value } }
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
            prepopulated_value: prepopulatedInput ? prepopulatedInput.value.trim() : ''
        };
    });

    return currentState;
}

// ============================================================
// UI HELPERS
// ============================================================

// ===== Update Save Button =====
function updateSaveButton() {
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) saveBtn.disabled = !hasChanges;
}


// ============================================================
// 2. BUILD INITIAL MAPPINGS
// ============================================================

/**
 * Builds the initial state from backend data
 * @param {Object} supplierMappings - { targetName: { source_field, is_mandatory, prepopulated_value } }
 * @param {Array} targetFields - [{ field_name, id, is_nullable, data_type }]
 * @returns {Object} initialState - { targetName: { source_field, is_mandatory, prepopulated_value } }
 */
function buildInitialMappings(supplierMappings, targetFields) {
    const initialState = {};

    (targetFields || []).forEach(target => {
        const targetName = target.field_name;
        const mapping = supplierMappings[targetName] || {};
        initialState[targetName] = {
            source_field: mapping.source_field || null,
            is_mandatory: mapping.is_mandatory || false,
            prepopulated_value: mapping.prepopulated_value || ''
        };
    });

    return initialState;
}


// ============================================================
// 3. DETECT CHANGES
// ============================================================

/**
 * Compares current state with initial state and returns changes
 * @param {Object} currentState - from collectMappingsFromUI()
 * @param {Object} initialState - from buildInitialMappings()
 * @returns {Array} changes - [{ target_name, target_id, source_field, is_mandatory, prepopulated_value, was_removed }]
 */
function detectChanges(currentState, initialState) {
    const changes = [];

    // Combine keys from both states
    const allTargets = new Set([
        ...Object.keys(currentState),
        ...Object.keys(initialState)
    ]);

    for (const targetName of allTargets) {
        const cur = currentState[targetName] || { source_field: null, is_mandatory: false, prepopulated_value: '' };
        const init = initialState[targetName] || { source_field: null, is_mandatory: false, prepopulated_value: '' };

        // Check if any field changed
        const sourceChanged = cur.source_field !== init.source_field;
        const mandatoryChanged = cur.is_mandatory !== init.is_mandatory;
        const prepopulatedChanged = cur.prepopulated_value !== init.prepopulated_value;

        if (sourceChanged || mandatoryChanged || prepopulatedChanged) {
            // was_removed: source was previously set, now cleared, AND no prepopulated value (mandatory fields can't be removed)
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
                // Store initial values for deletion or reference
                _initial_source: init.source_field,
                _initial_mandatory: init.is_mandatory,
                _initial_prepopulated: init.prepopulated_value
            });
        }
    }

    return changes;
}


// ============================================================
// 4. VALIDATE MAPPINGS
// ============================================================

/**
 * Validates mappings (duplicate source fields, mandatory fields with no value)
 * @param {Array} mappings - Array of mapping objects to validate
 * @returns {Array} errors - [{ target_name, message }]
 */
function validateMappings(mappings) {
    const errors = [];
    const seenSources = new Set();

    mappings.forEach((m, index) => {
        // Validate target_id
        if (!m.target_id || m.target_id <= 0 || isNaN(m.target_id)) {
            errors.push({
                target_name: m.target_name || `Row ${index + 1}`,
                message: `Invalid target ID (${m.target_id})`
            });
        }

        // Validate source_field uniqueness
        if (m.source_field && m.source_field.trim() !== '') {
            const key = m.source_field.trim();
            if (seenSources.has(key)) {
                errors.push({
                    target_name: m.target_name || `Row ${index + 1}`,
                    message: `Duplicate source field "${key}"`
                });
            }
            seenSources.add(key);
        }

        // ✅ Mandatory fields must have source OR prepopulated value
        if (m.is_mandatory) {
            const hasSource = m.source_field && m.source_field.trim() !== '';
            const hasPrepop = m.prepopulated_value && m.prepopulated_value.trim() !== '';
            if (!hasSource && !hasPrepop) {
                errors.push({
                    target_name: m.target_name || `Row ${index + 1}`,
                    message: 'Mandatory field requires either a source field or a prepopulated value.'
                });
            }
        }
    });

    return errors;
}


// ============================================================
// 5. SAVE MAPPINGS WITH API
// ============================================================

/**
 * Saves mappings to the server (POST for updates, DELETE for removals)
 * @param {string} supplierName - Name of the supplier
 * @param {Array} toUpdate - Mappings to create/update
 * @param {Array} toDelete - Mappings to delete
 * @param {Object} callbacks - { onProgress, onSuccess, onError, onComplete }
 * @returns {Promise} - Resolves with { successCount, failureCount, failedItems }
 */
async function saveMappingsWithAPI(supplierName, toUpdate, toDelete, callbacks = {}) {
    const {
        onProgress = null,
        onSuccess = null,
        onError = null,
        onComplete = null
    } = callbacks;

    const total = toUpdate.length + toDelete.length;
    let completed = 0;
    let successCount = 0;
    let failureCount = 0;
    const failedItems = [];

    // Progress callback
    if (onProgress) {
        onProgress(0, total);
    }

    // Helper: update progress
    function updateProgress() {
        completed++;
        if (onProgress) {
            onProgress(completed, total);
        }
    }

    // Helper: process response
    function processResponse(response, type, target) {
        updateProgress();
        if (response.ok) {
            successCount++;
            return { success: true };
        } else {
            failureCount++;
            let error = `HTTP ${response.status}`;
            failedItems.push({ target, error, status: response.status });
            return { success: false, error };
        }
    }

    // Build promises for each operation
    const promises = [];

    // DELETE operations
    for (const del of toDelete) {
        const initSource = del._initial_source;
        if (initSource) {
            promises.push(
                fetch(`/api/mappings/${encodeURIComponent(supplierName)}/${encodeURIComponent(initSource)}`, {
                    method: 'DELETE',
                })
                    .then(res => {
                        // 404 means already gone – treat as success
                        if (res.status === 404) {
                            successCount++;
                            updateProgress();
                            return { success: true, target: del.target_name, status: 204 };
                        }
                        return {
                            success: res.ok,
                            target: del.target_name,
                            response: res,
                            status: res.status
                        };
                    })
                    .catch(err => {
                        failureCount++;
                        updateProgress();
                        failedItems.push({ target: del.target_name, error: err.message || 'Network error' });
                        return { success: false, target: del.target_name, error: err.message };
                    })
            );
        }
    }

    // POST operations (updates/creates)
    for (const upd of toUpdate) {
        const formData = new FormData();
        formData.append('source_field', upd.source_field || '');
        formData.append('target_field_id', upd.target_id);
        formData.append('is_active', 'true');
        formData.append('is_mandatory', upd.is_mandatory ? 'true' : 'false');
        formData.append('prepopulated_value', upd.prepopulated_value || '');

        promises.push(
            fetch(`/api/mappings/${encodeURIComponent(supplierName)}`, {
                method: 'POST',
                body: formData
            })
                .then(res => {
                    updateProgress();
                    if (res.ok) {
                        successCount++;
                        return { success: true, target: upd.target_name, response: res };
                    } else {
                        failureCount++;
                        let error = `HTTP ${res.status}`;
                        failedItems.push({ target: upd.target_name, error, status: res.status });
                        return { success: false, target: upd.target_name, response: res, error };
                    }
                })
                .catch(err => {
                    failureCount++;
                    updateProgress();
                    failedItems.push({ target: upd.target_name, error: err.message || 'Network error' });
                    return { success: false, target: upd.target_name, error: err.message };
                })
        );
    }

    // Wait for all operations
    const results = await Promise.allSettled(promises);

    // Process results (count successes/failures already tracked above)
    const finalResults = {
        successCount,
        failureCount,
        failedItems,
        total,
        completed
    };

    // Callbacks
    if (failureCount > 0) {
        if (onError) onError(finalResults);
    } else {
        if (onSuccess) onSuccess(finalResults);
    }

    if (onComplete) onComplete(finalResults);

    return finalResults;
}

// ============================================================
// 6. HIGHLIGHT ERROR ROWS
// ============================================================

/**
 * Highlights rows with validation errors
 * @param {Array} errors - Array of error objects with target_name
 */
function highlightErrorRows(errors) {
    // Clear previous highlights
    document.querySelectorAll('.table-danger').forEach(el => el.classList.remove('table-danger'));

    errors.forEach(err => {
        // Find row by target name
        const row = document.querySelector(`tr:has(.source-select[data-target-name="${err.target_name}"])`);
        if (row) {
            row.classList.add('table-danger');
        }
    });
}


// ============================================================
// 7. SCROLL TO FIRST ERROR
// ============================================================

/**
 * Scrolls to the first highlighted error row
 */
function scrollToFirstError() {
    const firstErrorRow = document.querySelector('.table-danger');
    if (firstErrorRow) {
        firstErrorRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// ============================================================
// Detect if this is a new supplier (multiple checks)
// ============================================================
function isNewSupplierPage() {
    // Check 1: Does #page-data exist with supplierId?
    const pageDataEl = document.getElementById('page-data');
    if (pageDataEl && pageDataEl.dataset.supplierId) {
        return false;  // Edit page
    }

    // Check 2: Does supplier name input exist?
    if (document.getElementById('supplierName')) {
        return true;   // Add page
    }

    // Check 3: Check URL path
    if (window.location.pathname.includes('/add-mapping')) {
        return true;   // Add page
    }

    // Default: assume new supplier
    return true;
}


// ============================================================
// 8. SHOW VALIDATION ERRORS IN UI
// ============================================================

/**
 * Renders validation errors in the status area
 * @param {HTMLElement} statusDiv - The status div element
 * @param {Array} errors - Array of error objects
 */
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
// SAVE MAPPINGS – WITH TARGET NAME
// ============================================================

async function saveMappings() {
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('saveStatus');

    // ============================================================
    // Step 1: Get supplier name
    // ============================================================
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
        statusDiv.innerHTML = '<span class="text-danger">❌ Supplier name not found. Please enter a name.</span>';
        showToast('Error', 'Supplier name not found', 'danger');
        return;
    }

    console.log('📌 Supplier Name:', supplierName);

    // ============================================================
    // Step 2: Get page data
    // ============================================================
    const pageData = getPageData();
    console.log('📌 Page Data:', pageData);

    // ============================================================
    // Step 3: Determine source fields
    // ============================================================
    // ✅ Use backend source_fields if available, otherwise use parsedFileColumns
    let sourceFields = [];

    if (pageData?.sourceFields && pageData.sourceFields.length > 0) {
        // Edit page: source_fields from backend
        sourceFields = pageData.sourceFields;
        console.log('📌 Using source_fields from backend:', sourceFields);
    } else if (parsedFileColumns && parsedFileColumns.length > 0) {
        // Add page: source_fields from parsed file
        sourceFields = parsedFileColumns;
        console.log('📌 Using parsedFileColumns:', sourceFields);
    } else {
        // Fallback: try to get from data attribute
        const sourceFieldsEl = document.getElementById('page-data');
        if (sourceFieldsEl) {
            try {
                const sourceData = JSON.parse(sourceFieldsEl.dataset.sourceFields || '[]');
                if (sourceData.length > 0) {
                    sourceFields = sourceData;
                    console.log('📌 Using source_fields from data attribute:', sourceFields);
                }
            } catch (e) {
                console.warn('Could not parse source_fields from data attribute');
            }
        }
    }

    // ============================================================
    // Step 4: Collect current state from UI
    // ============================================================
    const currentState = collectMappingsFromUI();
    console.log('📌 Current State:', currentState);

    // ============================================================
    // Step 5: Ensure initialMappings exists
    // ============================================================
    if (!initialMappings || Object.keys(initialMappings).length === 0) {
        initialMappings = JSON.parse(JSON.stringify(currentState));
        console.log('⚠️ initialMappings was empty – set to currentState');
    }

    // ============================================================
    // Step 6: Detect changes
    // ============================================================
    const changes = detectChanges(currentState, initialMappings);
    console.log('📌 Changes detected:', changes);

    if (changes.length === 0) {
        statusDiv.innerHTML = '<span class="text-info">ℹ️ No changes to save.</span>';
        showToast('Info', 'No changes to save', 'info');
        return;
    }

    // ============================================================
    // Step 7: Validate mandatory fields
    // ============================================================
    const mandatoryErrors = validateMandatoryFields(currentState);
    if (mandatoryErrors.length > 0) {
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
        is_active: true,
        is_mandatory: state.is_mandatory || false,
        prepopulated_value: state.prepopulated_value || ''
    }));

    console.log(`📦 Total mappings to save: ${mappingList.length}`);

    if (mappingList.length === 0) {
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

    // ============================================================
    // Step 10: Build payload
    // ============================================================
    const payload = {
        source_fields: sourceFields,  // ✅ Now uses backend source_fields
        mappings: mappingList,
        is_new_supplier: isNewSupplierPage()
    };

    console.log('📦 Sending payload:', JSON.stringify(payload, null, 2));
    console.log('📌 source_fields:', sourceFields);
    console.log('📌 is_new_supplier:', payload.is_new_supplier);

    // ============================================================
    // Step 11: Send to backend
    // ============================================================
    saveBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-info">⏳ Saving ${mappingList.length} mapping(s)...</span>`;

    try {
        const response = await fetch(`/api/mappings/${encodeURIComponent(supplierName)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        console.log('📌 Response status:', response.status);

        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            let errorDetail = null;

            try {
                const errorData = await response.json();
                console.error('📌 Backend error response:', errorData);
                errorDetail = errorData;
                errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
            } catch (e) {
                errorMessage = response.statusText || errorMessage;
            }

            throw { message: errorMessage, detail: errorDetail, status: response.status };
        }

        const result = await response.json();
        console.log('✅ Save successful:', result);

        hasChanges = false;
        updateSaveButton();

        statusDiv.innerHTML = `<span class="text-success">✅ ${mappingList.length} mappings saved successfully!</span>`;
        showToast('Success', `Mappings saved for ${supplierName}`, 'success');
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Changes';

        setTimeout(() => {
            if (result.supplier_id) {
                window.location.href = `/show-mapping/${result.supplier_id}`;
            } else {
                window.location.reload();
            }
        }, 1500);

    } catch (error) {
        console.error('❌ Save failed:', error);

        const errorMsg = error.detail ? JSON.stringify(error.detail) : error.message;
        statusDiv.innerHTML = `<span class="text-danger">❌ ${errorMsg}</span>`;
        showToast('Error', `Failed to save mappings: ${error.message}`, 'danger');
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Changes';
    }
}



// ============================================================
// 9. SHOW SAVE RESULTS IN UI
// ============================================================

/**
 * Renders save results in the status area
 * @param {HTMLElement} statusDiv - The status div element
 * @param {Object} results - { successCount, failureCount, failedItems }
 */
function renderSaveResults(statusDiv, results) {
    if (!statusDiv) return;

    const { successCount, failureCount, failedItems } = results;

    if (failureCount > 0) {
        let html = `<div class="text-danger"><strong>❌ ${failureCount} operation(s) failed</strong></div>`;
        html += `<div class="text-success">✅ ${successCount} operation(s) succeeded</div>`;
        html += `<div class="mt-2"><small>Check console for full details</small></div>`;
        if (failedItems.length > 0) {
            html += `<button class="btn btn-sm btn-warning mt-2" onclick="window._retryFailedMappings()">🔄 Retry Failed</button>`;
            // Store failed items for retry
            window._failedItems = failedItems;
        }
        statusDiv.innerHTML = html;
    } else {
        statusDiv.innerHTML = `<span class="text-success">✅ All ${successCount} changes saved successfully!</span>`;
    }
}

/**
 * Validates mandatory fields in the current state.
 * Returns an array of errors for mandatory fields missing both source and prepopulated value.
 * @param {Object} currentState - from collectMappingsFromUI()
 * @param {Object} targetFieldsMap - optional mapping of target_id to is_nullable? We can use currentState's is_mandatory flag.
 * @returns {Array} errors - [{ target_name, message }]
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

// Make functions available globally
window.collectMappingsFromUI = collectMappingsFromUI;
window.buildInitialMappings = buildInitialMappings;
window.detectChanges = detectChanges;
window.validateMappings = validateMappings;
window.saveMappingsWithAPI = saveMappingsWithAPI;
window.highlightErrorRows = highlightErrorRows;
window.scrollToFirstError = scrollToFirstError;
window.renderValidationErrors = renderValidationErrors;
window.renderSaveResults = renderSaveResults;
