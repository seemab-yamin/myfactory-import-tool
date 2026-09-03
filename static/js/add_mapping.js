// ===== State =====
let parsedColumns = [];
let targetColumns = [];           // Full schema: [{id, name, nullable, type, ...}]
let mandatoryFields = [];         // Dynamic: fields where nullable === false
let currentMappings = {};
let supplierExists = false;
let prepopulatedValues = {};
let allSupplierNames = [];

// ===== Step Unlock State =====
let step1Complete = false;
let step2Complete = false;

// ===== DOM References =====
const supplierNameInput = document.getElementById('supplierName');
const sampleFileInput = document.getElementById('sampleFile');
const parseFileBtn = document.getElementById('parseFileBtn');
const mappingArea = document.getElementById('mappingArea');
const noFileMessage = document.getElementById('noFileMessage');
const saveBtn = document.getElementById('saveBtn');

// ============================================================
// STEP MANAGEMENT
// ============================================================
function updateStepStates() {
    const name = supplierNameInput.value.trim();
    step1Complete = name.length > 0 && !supplierExists;

    sampleFileInput.disabled = !step1Complete;
    parseFileBtn.disabled = !step1Complete;

    const mappingSelects = document.querySelectorAll('.source-select');
    const prepopulatedInputs = document.querySelectorAll('.prepopulated-value');
    mappingSelects.forEach(select => select.disabled = !step2Complete);
    prepopulatedInputs.forEach(input => input.disabled = !step2Complete);

    updateStepIndicators();
}

function updateStepIndicators() {
    document.querySelectorAll('[data-step]').forEach(card => {
        const step = parseInt(card.dataset.step);
        const isActive = (step === getCurrentStep());
        const isCompleted = (step < getCurrentStep());
        card.classList.toggle('active', isActive);
        card.classList.toggle('completed', isCompleted);
    });

    updateStepStatus(1, step1Complete, 'Enter supplier name', 'Name already exists');
    updateStepStatus(2, step2Complete, 'Upload a file', '');
}

function getCurrentStep() {
    if (!step1Complete) return 1;
    if (!step2Complete) return 2;
    return 3;
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
// FETCH SUPPLIERS & UNIQUENESS
// ============================================================
async function fetchAllSuppliers() {
    try {
        const response = await fetch('/api/mappings-list');
        if (!response.ok) throw new Error('Failed to fetch suppliers');
        const data = await response.json();
        const suppliers = data.suppliers || [];
        allSupplierNames = suppliers.map(s => s[1]).filter(Boolean);
        console.log('✅ Cached supplier names:', allSupplierNames);
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
    const name = input.value.trim();

    if (!name) {
        input.classList.remove('is-invalid', 'is-valid');
        supplierExists = false;
        updateStepStates();
        return;
    }

    const exists = allSupplierNames.includes(name);

    if (exists) {
        input.classList.add('is-invalid');
        input.classList.remove('is-valid');
        feedback.textContent = '⚠️ This supplier name already exists. Please choose a different name.';
        supplierExists = true;
    } else {
        input.classList.remove('is-invalid');
        input.classList.add('is-valid');
        feedback.textContent = '✅ Name is available';
        supplierExists = false;
    }

    updateStepStates();
}

async function checkAvailability() {
    await fetchAllSuppliers();
    checkSupplierName();
}

// ============================================================
// FETCH SCHEMA & FILE PARSING
// ============================================================
async function fetchTargetSchema() {
    try {
        const response = await fetch('/api/schema');
        if (!response.ok) throw new Error('Failed to fetch schema');
        const data = await response.json();
        const allColumns = data.columns || [];
        const excludedColumns = ['ProductID'];
        targetColumns = allColumns.filter(col => !excludedColumns.includes(col.name));

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

async function parseSampleFile() {
    const fileInput = document.getElementById('sampleFile');
    const statusDiv = document.getElementById('parseStatus');
    const previewDiv = document.getElementById('filePreview');

    if (!fileInput.files.length) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Please select a file</span>';
        return;
    }

    const supplierName = document.getElementById('supplierName').value.trim();
    if (!supplierName) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Please enter a supplier name first</span>';
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    formData.append('supplier_name', supplierName);

    statusDiv.innerHTML = '<span class="text-info">⏳ Uploading & parsing...</span>';

    try {
        const response = await fetch('/api/parse-sample', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Parse failed');
        }

        const data = await response.json();
        parsedColumns = data.columns || [];
        const preview = data.preview || [];
        const supplierId = data.supplier_id;

        previewDiv.style.display = 'block';
        renderPreview(preview);

        step2Complete = true;
        buildMappingUI(targetColumns, parsedColumns);

        statusDiv.innerHTML = `<span class="text-success">✅ Parsed ${parsedColumns.length} columns</span>`;
        showToast('Success', `Parsed ${parsedColumns.length} columns`, 'success');

        window.supplierId = supplierId;
    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
    }

    updateStepStates();
}

async function forceRefreshSchema() {
    const btn = document.getElementById('refreshSchemaBtn');
    const statusDiv = document.getElementById('parseStatus');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Refreshing...';
    statusDiv.innerHTML = '<span class="text-info">⏳ Refreshing schema from database...</span>';

    try {
        const response = await fetch('/api/schema?refresh_cache=true&use_cache=false');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        await fetchTargetSchema();

        if (parsedColumns.length > 0) {
            buildMappingUI(targetColumns, parsedColumns);
        }
        statusDiv.innerHTML = '<span class="text-success">✅ Schema refreshed successfully!</span>';
        showToast('Schema refreshed successfully', 'success');
    } catch (error) {
        statusDiv.innerHTML = `<span class="text-danger">❌ Failed to refresh schema: ${error.message}</span>`;
        showToast('Error', `Failed to refresh schema: ${error.message}`, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Force Refresh Schema';
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
    body.innerHTML = rows.map(row => `
        <tr>${headers.map(h => `<td>${row[h] || ''}</td>`).join('')}</tr>
    `).join('');
}

// ============================================================
// BUILD MAPPING UI
// ============================================================
function buildMappingUI(targetCols, fileCols) {
    const tbody = document.getElementById('mappingTableBody');
    mappingArea.style.display = 'block';
    noFileMessage.style.display = 'none';
    currentMappings = {};
    prepopulatedValues = {};

    const sortedTargetCols = [...targetCols].sort((a, b) => {
        const aRequired = a.nullable === false;
        const bRequired = b.nullable === false;
        if (aRequired && !bRequired) return -1;
        if (!aRequired && bRequired) return 1;
        return 0;
    });

    let html = '';
    sortedTargetCols.forEach((col, index) => {
        const isMandatory = col.nullable === false;
        const rowId = `row-${index}`;
        const fieldId = col.target_field_id;

        html += `<tr id="${rowId}">
                <td>${index + 1}</td>
                <td>
                    <strong>${col.name}</strong>
                    ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                    <br><span class="text-muted small">${col.type || ''}</span>
                    <br><span class="text-muted small">ID: ${fieldId}</span>
                </td>
                <td>
                    <select class="form-select form-select-sm source-select" data-target-id="${fieldId}">
                        <option value="">— ignore —</option>   <!-- ✅ Changed to empty string -->
                        ${fileCols.map(fc => `<option value="${fc}">${fc}</option>`).join('')}
                    </select>
                </td>
                <td class="text-center">
                    <input type="checkbox" class="form-check-input mandatory-check" data-target-id="${fieldId}" 
                        ${isMandatory ? 'checked disabled' : ''}>
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm prepopulated-value"
                        data-target-id="${fieldId}" placeholder="Pre Populated value...">
                </td>
            </tr>`;
    });

    tbody.innerHTML = html;
    step2Complete = true;

    // Event listeners
    document.querySelectorAll('.source-select').forEach(select => {
        select.addEventListener('change', function () {
            const targetId = parseInt(this.dataset.targetId);
            const sourceColumn = this.value;
            updateMapping(targetId, sourceColumn);
        });
    });

    document.querySelectorAll('.mandatory-check').forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            const targetId = parseInt(this.dataset.targetId);
            const isChecked = this.checked;

            if (isChecked) {
                if (!mandatoryFields.includes(targetId)) {
                    mandatoryFields.push(targetId);
                }
            } else {
                const col = targetColumns.find(c => c.target_field_id === targetId);
                if (col && col.nullable !== false) {
                    mandatoryFields = mandatoryFields.filter(id => id !== targetId);
                } else if (col && col.nullable === false) {
                    this.checked = true;
                    showToast('Warning', 'This field is required by the database and cannot be made optional', 'warning');
                    return;
                }
            }

            updateValidation(targetId);
            showMandatorySummary();
            updateMappingStatus();
        });
    });

    document.querySelectorAll('.prepopulated-value').forEach(input => {
        input.addEventListener('input', function () {
            const targetId = parseInt(this.dataset.targetId);
            const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);

            if (this.value.trim()) {
                prepopulatedValues[targetId] = this.value.trim();
            } else {
                delete prepopulatedValues[targetId];
            }

            updateMapping(targetId, sourceSelect ? sourceSelect.value : null);
        });
    });

    showMandatorySummary();
    updateMappingStatus();
    updateStepStates();
}

// ============================================================
// UI UPDATE FUNCTIONS
// ============================================================

function updateMapping(targetId, sourceColumn) {
    const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);
    const valueInput = document.querySelector(`.prepopulated-value[data-target-id="${targetId}"]`);

    delete currentMappings[targetId];

    const hasSource = sourceColumn && sourceColumn !== '';
    const hasPrepopulated = valueInput && valueInput.value.trim() !== '';

    currentMappings[targetId] = {
        source: hasSource ? sourceColumn : null,
        prepopulated: hasPrepopulated,
        value: hasPrepopulated ? valueInput.value.trim() : null
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

    const hasSource = sourceSelect && sourceSelect.value && sourceSelect.value !== '';
    const hasPrepopulated = valueInput && valueInput.value.trim() !== '';

    if (!hasSource && !hasPrepopulated) {
        if (sourceSelect) sourceSelect.classList.add('is-invalid');
        if (valueInput) valueInput.classList.add('is-invalid');
    } else {
        if (sourceSelect) sourceSelect.classList.remove('is-invalid');
        if (valueInput) valueInput.classList.remove('is-invalid');
        if (sourceSelect && hasSource) sourceSelect.classList.add('is-valid');
    }
}

function showMandatorySummary() {
    const summaryDiv = document.getElementById('mandatorySummary');
    const listSpan = document.getElementById('mandatoryList');

    const mandatoryNames = targetColumns
        .filter(col => mandatoryFields.includes(col.target_field_id))
        .map(col => col.name);

    if (mandatoryNames.length > 0) {
        summaryDiv.style.display = 'block';
        listSpan.innerHTML = mandatoryNames.map(f =>
            `<span class="badge bg-danger me-1">${f}</span>`
        ).join('');
    } else {
        summaryDiv.style.display = 'none';
    }
}

function updateMappingStatus() {
    const statusBadge = document.getElementById('mappingStatus');
    const saveBtn = document.getElementById('saveBtn');

    const totalMapped = Object.keys(currentMappings).length;
    const totalRequired = mandatoryFields.length;

    const mandatoryMapped = mandatoryFields.every(id => {
        const mapping = currentMappings[id];
        if (!mapping) return false;
        return (mapping.source && mapping.source !== '') || (mapping.prepopulated && mapping.value);
    });

    const canSave = mandatoryMapped && totalMapped > 0;

    statusBadge.textContent = `${totalMapped}/${targetColumns.length} mapped (${totalMapped}/${totalRequired} required)`;
    statusBadge.className = `badge ${canSave ? 'bg-success' : 'bg-warning text-dark'}`;
    saveBtn.disabled = !canSave;
}

// ============================================================
// SAVE MAPPINGS – USING SHARED UTILITIES
// ============================================================

async function saveMappings() {
    const supplierName = document.getElementById('supplierName').value.trim();
    const statusDiv = document.getElementById('saveStatus');
    const saveBtn = document.getElementById('saveBtn');

    // 1. Basic validation
    if (!supplierName) {
        showToast('Error', 'Please enter a supplier name', 'danger');
        document.getElementById('supplierName').focus();
        return;
    }
    if (supplierExists) {
        showToast('Error', 'Supplier name already exists. Please choose a different name.', 'danger');
        return;
    }

    // 2. Collect current state from UI using the shared utility
    const currentState = collectMappingsFromUI();

    // 3. Validate mandatory fields
    const mandatoryErrors = validateMandatoryFields(currentState);
    if (mandatoryErrors.length > 0) {
        highlightErrorRows(mandatoryErrors);
        renderValidationErrors(statusDiv, mandatoryErrors);
        showToast('Validation Error', `${mandatoryErrors.length} error(s) found.`, 'danger');
        scrollToFirstError();
        return;
    }

    // 4. Build the list of mappings to save
    const toUpdate = Object.entries(currentState)
        .filter(([_, state]) => state.source_field || state.prepopulated_value)
        .map(([targetName, state]) => ({
            target_id: state.target_id,
            target_name: targetName,
            source_field: state.source_field || `__prepopulated__${targetName}`,
            is_mandatory: state.is_mandatory,
            prepopulated_value: state.prepopulated_value || ''
        }));

    if (toUpdate.length === 0) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ No mappings to save.</span>';
        showToast('Warning', 'No mappings to save.', 'warning');
        return;
    }

    // 5. Validate for duplicates and other issues
    const validationErrors = validateMappings(toUpdate);
    if (validationErrors.length > 0) {
        highlightErrorRows(validationErrors);
        renderValidationErrors(statusDiv, validationErrors);
        showToast('Validation Error', `${validationErrors.length} error(s) found.`, 'danger');
        scrollToFirstError();
        return;
    }

    // 6. Disable button and show spinner
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Saving...';
    statusDiv.innerHTML = `<span class="text-info">⏳ Saving ${toUpdate.length} mapping(s)...</span>`;

    try {
        // 7. Save using the shared API utility (no deletions for new supplier)
        const results = await saveMappingsWithAPI(supplierName, toUpdate, [], {
            onSuccess: async (res) => {
                renderSaveResults(statusDiv, res);
                showToast('Success', `All ${res.successCount} mappings saved successfully!`, 'success');
                await fetchAllSuppliers();
                setTimeout(() => {
                    window.location.href = `/show-mapping/${encodeURIComponent(window.supplierId)}`;
                }, 1500);
            },
            onError: (res) => {
                renderSaveResults(statusDiv, res);
                showToast('Partial Save', `${res.successCount} succeeded, ${res.failureCount} failed.`, 'warning');
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="bi bi-save"></i> Save';
            }
        });
    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save';
    }
}

// ============================================================
// RESET & INIT
// ============================================================

function resetForm() {
    document.getElementById('supplierName').value = '';
    document.getElementById('sampleFile').value = '';
    document.getElementById('parseStatus').innerHTML = '';
    document.getElementById('filePreview').style.display = 'none';
    document.getElementById('mappingArea').style.display = 'none';
    document.getElementById('noFileMessage').style.display = 'block';
    document.getElementById('saveStatus').innerHTML = '';
    document.getElementById('mappingStatus').textContent = '0 mapped';
    document.getElementById('mappingStatus').className = 'badge bg-warning text-dark';
    saveBtn.disabled = true;
    supplierExists = false;
    parsedColumns = [];
    currentMappings = {};
    prepopulatedValues = {};
    step1Complete = false;
    step2Complete = false;
    allSupplierNames = [];
    updateStepStates();
}

document.addEventListener('DOMContentLoaded', async function () {
    await fetchTargetSchema();
    await fetchAllSuppliers();

    supplierNameInput.addEventListener('input', checkSupplierName);
    sampleFileInput.addEventListener('change', function () {
        if (this.files.length) {
            document.getElementById('parseFileBtn').click();
        }
    });

    updateStepStates();
});