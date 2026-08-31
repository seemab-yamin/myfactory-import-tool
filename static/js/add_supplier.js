// ===== State =====
let parsedColumns = [];
let targetColumns = [];           // Full schema: [{name, nullable, type, ...}]
let targetColumnNames = [];       // Just names for dropdown
let mandatoryFields = [];         // Dynamic: fields where nullable === false
let currentMappings = {};
let supplierExists = false;
let prepopulatedValues = {};

// ===== Fetch Target Schema (Full) =====
async function fetchTargetSchema() {
    try {
        const response = await fetch('/api/schema');
        if (!response.ok) throw new Error('Failed to fetch schema');
        const data = await response.json();
        const allColumns = data.columns || [];
        const excludedColumns = ['ProductID'];
        targetColumns = allColumns.filter(col => !excludedColumns.includes(col.name));
        targetColumnNames = targetColumns.map(c => c.name);

        // Dynamically determine mandatory fields (NOT NULL)
        mandatoryFields = targetColumns
            .filter(c => c.nullable === false)
            .map(c => c.name);
        return targetColumns;
    } catch (e) {
        console.error('Error fetching schema:', e);
        showToast('Error', 'Failed to load product schema', 'danger');
        return [];
    }
}

// ===== Parse Sample File =====
async function parseSampleFile() {
    const fileInput = document.getElementById('sampleFile');
    const statusDiv = document.getElementById('parseStatus');
    const previewDiv = document.getElementById('filePreview');

    if (!fileInput.files.length) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ Please select a file</span>';
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

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

        // Show preview
        previewDiv.style.display = 'block';
        renderPreview(preview);

        // Build mapping UI (Database → File)
        buildMappingUI(targetColumns, parsedColumns);

        statusDiv.innerHTML = `<span class="text-success">✅ Parsed ${parsedColumns.length} columns</span>`;
        showToast('Success', `Parsed ${parsedColumns.length} columns`, 'success');

    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
    }
}

// ===== Force Refresh Schema =====
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
        btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Force Refresh Schema';
    }
}
// ===== Render Preview =====
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

// ===== Build Mapping UI with Enhanced Columns =====
function buildMappingUI(targetCols, fileCols) {
    const area = document.getElementById('mappingArea');
    const noFile = document.getElementById('noFileMessage');
    const tbody = document.getElementById('mappingTableBody');
    area.style.display = 'block';
    noFile.style.display = 'none';
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
        html += `
            <tr id="${rowId}">
                <td>${index + 1}</td>
                <td>
                    <strong>${col.name}</strong>
                    ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                    <br><span class="text-muted small">${col.type || ''}</span>
                </td>
                <td>
                    <select class="form-select form-select-sm source-select" data-target="${col.name}" data-row="${rowId}">
                        <option value="">— ignore —</option>
                        ${fileCols.map(fc => `<option value="${fc}">${fc}</option>`).join('')}
                    </select>
                </td>
                <td class="text-center">
                    <input type="checkbox" class="form-check-input mandatory-check" data-target="${col.name}" 
                           ${isMandatory ? 'checked disabled' : ''}>
                </td>
                <td class="text-center">
                    <input type="checkbox" class="form-check-input prepopulated-check" data-target="${col.name}" data-row="${rowId}">
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm prepopulated-value"
                           data-target="${col.name}" placeholder="Default value..." disabled>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
    // Add event listeners
    document.querySelectorAll('.source-select').forEach(select => {
        select.addEventListener('change', function () {
            const targetField = this.dataset.target;
            const sourceColumn = this.value;
            const rowId = this.dataset.row;
            updateMapping(targetField, sourceColumn, rowId);
        });
    });
    document.querySelectorAll('.mandatory-check').forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            const targetField = this.dataset.target;
            updateValidation(targetField);
        });
    });
    document.querySelectorAll('.prepopulated-check').forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            const targetField = this.dataset.target;
            const rowId = this.dataset.row;
            const valueInput = document.querySelector(`.prepopulated-value[data-target="${targetField}"]`);
            if (this.checked) {
                valueInput.disabled = false;
                valueInput.focus();
            } else {
                valueInput.disabled = true;
                valueInput.value = '';
                delete prepopulatedValues[targetField];
            }
            updateMapping(targetField, null, rowId);
        });
    });
    document.querySelectorAll('.prepopulated-value').forEach(input => {
        input.addEventListener('input', function () {
            const targetField = this.dataset.target;
            if (this.value.trim()) {
                prepopulatedValues[targetField] = this.value.trim();
            } else {
                delete prepopulatedValues[targetField];
            }
            updateValidation(targetField);
        });
    });
    showMandatorySummary();
    updateMappingStatus();
}
// ===== Update Mapping =====
function updateMapping(targetField, sourceColumn, rowId) {
    const sourceSelect = document.querySelector(`.source-select[data-target="${targetField}"]`);
    const prepopulatedCheck = document.querySelector(`.prepopulated-check[data-target="${targetField}"]`);
    const valueInput = document.querySelector(`.prepopulated-value[data-target="${targetField}"]`);
    // Clear existing mapping
    delete currentMappings[targetField];
    // Case 1: Source field selected
    if (sourceColumn && sourceColumn !== '') {
        currentMappings[targetField] = { source: sourceColumn, prepopulated: false, value: null };
        // Uncheck prepopulated if source is selected
        if (prepopulatedCheck) {
            prepopulatedCheck.checked = false;
            valueInput.disabled = true;
            valueInput.value = '';
            delete prepopulatedValues[targetField];
        }
    }
    // Case 2: Prepopulated checked
    else if (prepopulatedCheck && prepopulatedCheck.checked) {
        const value = valueInput.value.trim();
        if (value) {
            currentMappings[targetField] = { source: null, prepopulated: true, value: value };
        } else {
            // Show error if prepopulated is checked but no value
            valueInput.classList.add('is-invalid');
        }
    }
    updateValidation(targetField);
    updateMappingStatus();
}
// ===== Update Validation for a Specific Field =====
function updateValidation(targetField) {
    const sourceSelect = document.querySelector(`.source-select[data-target="${targetField}"]`);
    const prepopulatedCheck = document.querySelector(`.prepopulated-check[data-target="${targetField}"]`);
    const valueInput = document.querySelector(`.prepopulated-value[data-target="${targetField}"]`);
    const isMandatory = mandatoryFields.includes(targetField);
    const rowId = sourceSelect ? sourceSelect.dataset.row : null;
    // Remove existing validation states
    if (sourceSelect) sourceSelect.classList.remove('is-invalid', 'is-valid');
    if (valueInput) valueInput.classList.remove('is-invalid', 'is-valid');
    // If not mandatory, skip validation
    if (!isMandatory) return;
    const hasSource = sourceSelect && sourceSelect.value && sourceSelect.value !== '';
    const hasPrepopulated = prepopulatedCheck && prepopulatedCheck.checked && valueInput && valueInput.value.trim();
    // Validate: either source is selected OR prepopulated has a value
    if (!hasSource && !hasPrepopulated) {
        if (sourceSelect) sourceSelect.classList.add('is-invalid');
        if (valueInput) valueInput.classList.add('is-invalid');
    } else {
        if (sourceSelect) sourceSelect.classList.remove('is-invalid');
        if (valueInput) valueInput.classList.remove('is-invalid');
        if (sourceSelect && hasSource) sourceSelect.classList.add('is-valid');
    }
}
// ===== Show Mandatory Fields Summary =====
function showMandatorySummary() {
    const summaryDiv = document.getElementById('mandatorySummary');
    const listSpan = document.getElementById('mandatoryList');
    if (mandatoryFields.length) {
        summaryDiv.style.display = 'block';
        listSpan.innerHTML = mandatoryFields.map(f =>
            `<span class="badge bg-danger me-1">${f}</span>`
        ).join('');
    } else {
        summaryDiv.style.display = 'none';
    }
}
// ===== Update Mapping Status =====
function updateMappingStatus() {
    const statusBadge = document.getElementById('mappingStatus');
    const saveBtn = document.getElementById('saveBtn');

    const totalMapped = Object.keys(currentMappings).length;
    const totalRequired = mandatoryFields.length;

    // Check if all mandatory fields are mapped
    const mandatoryMapped = mandatoryFields.every(f => {
        const mapping = currentMappings[f];
        if (!mapping) return false;
        return (mapping.source && mapping.source !== '') || (mapping.prepopulated && mapping.value);
    });

    const canSave = mandatoryMapped && totalMapped > 0;

    statusBadge.textContent = `${totalMapped}/${targetColumns.length} mapped (${totalMapped}/${totalRequired} required)`;
    statusBadge.className = `badge ${canSave ? 'bg-success' : 'bg-warning text-dark'}`;

    saveBtn.disabled = !canSave;
}

// ===== Save Mappings =====
async function saveMappings() {
    const supplierName = document.getElementById('supplierName').value.trim();
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('saveStatus');

    if (!supplierName) {
        showToast('Error', 'Please enter a supplier name', 'danger');
        document.getElementById('supplierName').focus();
        return;
    }

    if (supplierExists) {
        showToast('Error', 'Supplier name already exists. Please choose a different name.', 'danger');
        return;
    }

    // Check mandatory mappings
    const missingMandatory = mandatoryFields.filter(f => {
        const mapping = currentMappings[f];
        if (!mapping) return true;
        return !((mapping.source && mapping.source !== '') || (mapping.prepopulated && mapping.value));
    });

    if (missingMandatory.length) {
        showToast('Error', `Missing required fields: ${missingMandatory.join(', ')}`, 'danger');
        return;
    }

    saveBtn.disabled = true;
    statusDiv.innerHTML = '<span class="text-info">⏳ Saving mappings...</span>';

    try {
        for (const [targetField, mapping] of Object.entries(currentMappings)) {
            let sourceField = mapping.source;
            let targetValue = mapping.value;

            // If prepopulated, we need to handle it differently
            // We'll store the value in a special way or use a default
            if (mapping.prepopulated && mapping.value) {
                // For prepopulated values, we can store them as a special mapping
                // or set a default value in the database
                sourceField = '__prepopulated__';
                targetValue = mapping.value;
            }

            const formData = new FormData();
            formData.append('source_field', sourceField || '');
            formData.append('target_field', targetField);
            formData.append('active', 'true');
            if (targetValue) {
                formData.append('default_value', targetValue);
            }

            const response = await fetch(`/api/mappings/${supplierName}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to save mapping');
            }
        }

        statusDiv.innerHTML = '<span class="text-success">✅ Mappings saved successfully!</span>';
        showToast('Success', `Mappings saved for ${supplierName}`, 'success');

        setTimeout(() => {
            window.location.href = `/suppliers/${encodeURIComponent(supplierName)}`;
        }, 1500);

    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
        saveBtn.disabled = false;
    }
}

// ===== Check Supplier Name Uniqueness =====
async function checkSupplierName() {
    const input = document.getElementById('supplierName');
    const feedback = document.getElementById('supplierNameFeedback');
    const name = input.value.trim();

    if (!name) {
        input.classList.remove('is-invalid', 'is-valid');
        supplierExists = false;
        return;
    }

    try {
        const response = await fetch(`/api/mappings/${name}`);
        if (response.ok) {
            const data = await response.json();
            const exists = data.summary && data.summary.total > 0;
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
        } else {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
            feedback.textContent = '✅ Name is available';
            supplierExists = false;
        }
    } catch (e) {
        input.classList.remove('is-invalid', 'is-valid');
        feedback.textContent = '⚠️ Could not verify availability. Please try again.';
        supplierExists = false;
    }
}

// ===== Manual Check Availability =====
function checkAvailability() {
    checkSupplierName();
}

// ===== Reset Form =====
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
    document.getElementById('saveBtn').disabled = true;
    supplierExists = false;
    parsedColumns = [];
    currentMappings = {};
    prepopulatedValues = {};
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', async function () {
    await fetchTargetSchema();

    document.getElementById('supplierName').addEventListener('input', checkSupplierName);
    document.getElementById('sampleFile').addEventListener('change', function () {
        if (this.files.length) {
            document.getElementById('parseFileBtn').click();
        }
    });
});