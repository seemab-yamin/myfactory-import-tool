// ===== State =====
let parsedColumns = [];
let targetColumns = [];
let mandatoryFields = [];
let currentMappings = {};
let supplierExists = false;
let prepopulatedValues = {};
let allSupplierNames = [];
let hasChanges = false;

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
        allSupplierNames = suppliers.map(s => s[1].toLowerCase()).filter(Boolean);
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

        previewDiv.style.display = 'block';
        renderPreview(preview);

        step2Complete = true;
        buildMappingUI(targetColumns, parsedColumns);

        statusDiv.innerHTML = `<span class="text-success">✅ Parsed ${parsedColumns.length} columns</span>`;
        showToast('Success', `Parsed ${parsedColumns.length} columns`, 'success');

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
// BUILD MAPPING UI (updated event listeners)
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
        const fieldName = col.name || col.field_name || 'Unknown';

        // ✅ Store initial state with target name
        currentMappings[fieldId] = {
            target: fieldName,        // ← Added: store the field name
            source: null,
            prepopulated: false,
            prepopulated_value: null
        };

        html += `<tr id="${rowId}">
                <td>${index + 1}</td>
                <td>
                    <strong>${fieldName}</strong>
                    ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                    <br><span class="text-muted small">${col.type || ''}</span>
                    <br><span class="text-muted small">ID: ${fieldId}</span>
                </td>
                <td>
                    <select class="form-select form-select-sm source-select" data-target-id="${fieldId}" data-target-name="${fieldName}">
                        <option value="None">None</option>
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

    // --- Event listeners with markDirty ---
    document.querySelectorAll('.source-select').forEach(select => {
        select.addEventListener('change', function () {
            const targetId = parseInt(this.dataset.targetId);
            const sourceColumn = this.value;
            updateMapping(targetId, sourceColumn);
            markDirty();
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
            markDirty();
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
            markDirty();
        });
    });

    // ✅ Store target fields globally for validation
    window._mappingTargets = sortedTargetCols.reduce((acc, col) => {
        acc[col.target_field_id] = col.name || col.field_name || 'Unknown';
        return acc;
    }, {});

    updateMappingStatus();
    updateStepStates();
}

// ============================================================
// UI UPDATE FUNCTIONS
// ============================================================

function updateMapping(targetId, sourceColumn) {
    const sourceSelect = document.querySelector(`.source-select[data-target-id="${targetId}"]`);
    const prepopulatedValueInput = document.querySelector(`.prepopulated-value[data-target-id="${targetId}"]`);

    // ✅ Gets target name from data attribute
    const targetName = sourceSelect ? sourceSelect.dataset.targetName : null;

    delete currentMappings[targetId];

    const hasSource = sourceColumn && sourceColumn !== '' && sourceColumn !== 'None';
    const hasPrepopulated = prepopulatedValueInput && prepopulatedValueInput.value.trim() !== '';

    currentMappings[targetId] = {
        target: targetName,
        source: hasSource ? sourceColumn : null,
        prepopulated: hasPrepopulated,
        prepopulated_value: hasPrepopulated ? prepopulatedValueInput.value.trim() : null
    };

    updateValidation(targetId);
    updateMappingStatus();  // will check hasChanges
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


function updateMappingStatus() {
    const statusBadge = document.getElementById('mappingStatus');
    const saveBtn = document.getElementById('saveBtn');

    const totalMapped = Object.keys(currentMappings).length;
    const totalRequired = mandatoryFields.length;

    const mandatoryMapped = mandatoryFields.every(id => {
        const mapping = currentMappings[id];
        if (!mapping) return false;
        return (mapping.source && mapping.source !== '') || (mapping.prepopulated && mapping.prepopulated_value);
    });

    // ✅ Save button only enabled if there are changes AND mandatory fields are valid
    const canSave = hasChanges && mandatoryMapped && totalMapped > 0;

    statusBadge.textContent = `${totalMapped}/${targetColumns.length} mapped (${totalMapped}/${totalRequired} required)`;
    statusBadge.className = `badge ${canSave ? 'bg-success' : 'bg-warning text-dark'}`;
    saveBtn.disabled = !canSave;
}

// ============================================================
// MARK DIRTY
// ============================================================

function markDirty() {
    hasChanges = true;
    updateMappingStatus();
}

// ============================================================
// SAVE MAPPINGS – WITH TARGET NAME
// ============================================================

async function saveMappings() {
    const supplierName = document.getElementById('supplierName').value.trim();
    const statusDiv = document.getElementById('saveStatus');
    const saveBtn = document.getElementById('saveBtn');

    // -------- VALIDATION BLOCK --------
    if (!supplierName) {
        showToast('Error', 'Please enter a supplier name', 'danger');
        document.getElementById('supplierName').focus();
        return;
    }
    if (supplierExists) {
        showToast('Error', 'Supplier name already exists. Please choose a different name.', 'danger');
        return;
    }

    const missingMandatory = mandatoryFields.filter(id => {
        const mapping = currentMappings[id];
        if (!mapping) return true;
        return !((mapping.source && mapping.source !== '') || (mapping.prepopulated_value && mapping.prepopulated_value !== ''));
    });

    if (missingMandatory.length) {
        const missingNames = missingMandatory.map(id => {
            const col = targetColumns.find(c => c.target_field_id === id);
            return col ? col.name : id;
        });
        showToast('Error', `Missing required fields: ${missingNames.join(', ')}`, 'danger');
        return;
    }

    // -------- PREPARE DATA --------
    const mappingList = [];

    for (const [targetId, mapping] of Object.entries(currentMappings)) {
        console.log(`Preparing mapping for target field ID ${targetId}:`, mapping);

        const mappingItem = {
            target_field_name: mapping.target,
            source_field: mapping.source || '',
            target_field_id: parseInt(targetId),
            is_active: true,
            is_mandatory: mandatoryFields.includes(parseInt(targetId)),
        };

        if (mapping.prepopulated_value && mapping.prepopulated_value !== '') {
            mappingItem.prepopulated_value = mapping.prepopulated_value;
        }

        mappingList.push(mappingItem);
    }

    // ✅ Build payload matching backend signature
    const payload = {
        source_fields: parsedColumns || [],
        mapping: mappingList
    };

    console.log('📦 Sending payload:', payload);

    // -------- DISABLE BUTTON & SHOW LOADING --------
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Saving...';
    statusDiv.innerHTML = '<span class="text-info">⏳ Saving mappings...</span>';

    // -------- SEND REQUEST TO BACKEND --------
    try {
        const response = await fetch(`/api/mappings/${encodeURIComponent(supplierName)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        // -------- HANDLE RESPONSE --------
        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorMessage;
            } catch (e) {
                // If response is not JSON, use status text
                errorMessage = response.statusText || errorMessage;
            }
            throw new Error(errorMessage);
        }

        const result = await response.json();
        console.log('✅ Save successful:', result);

        // -------- SUCCESS FEEDBACK --------
        hasChanges = false;
        updateMappingStatus();

        statusDiv.innerHTML = `<span class="text-success">✅ Mappings saved successfully!</span>`;
        showToast('Success', `Mappings saved for ${supplierName}`, 'success');
        saveBtn.innerHTML = '<i class="bi bi-save"></i> Save';

        // Redirect to listings page after 1.5 seconds
        setTimeout(() => {
            window.location.href = '/mappings-list';
        }, 1500);

    } catch (error) {
        // -------- ERROR HANDLING --------
        console.error('❌ Save failed:', error);
        statusDiv.innerHTML = `<span class="text-danger">❌ ${error.message}</span>`;
        showToast('Error', `Failed to save mappings: ${error.message}`, 'danger');
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