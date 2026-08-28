// ===== State =====
let parsedColumns = [];
let targetColumns = [];
let mandatoryFields = ['ProductID', 'ProductNumber']; // Add required fields
let currentMappings = {};
let supplierExists = false;

// ===== Fetch Target Schema =====
async function fetchTargetSchema() {
    try {
        const response = await fetch('/schema/tdProducts/columns');
        if (!response.ok) throw new Error('Failed to fetch schema');
        const data = await response.json();
        targetColumns = data.columns || [];
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

        // Build mapping UI
        buildMappingUI(parsedColumns);

        statusDiv.innerHTML = `<span class="text-success">✅ Parsed ${parsedColumns.length} columns</span>`;
        showToast('Success', `Parsed ${parsedColumns.length} columns`, 'success');

    } catch (e) {
        statusDiv.innerHTML = `<span class="text-danger">❌ ${e.message}</span>`;
        showToast('Error', e.message, 'danger');
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

    // Headers
    const headers = Object.keys(preview[0]);
    head.innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;

    // Rows (first 5)
    const rows = preview.slice(0, 5);
    body.innerHTML = rows.map(row => `
        <tr>${headers.map(h => `<td>${row[h] || ''}</td>`).join('')}</tr>
    `).join('');
}

// ===== Build Mapping UI =====
function buildMappingUI(columns) {
    const area = document.getElementById('mappingArea');
    const noFile = document.getElementById('noFileMessage');
    const tbody = document.getElementById('mappingTableBody');

    area.style.display = 'block';
    noFile.style.display = 'none';

    // Reset mappings
    currentMappings = {};

    let html = '';
    columns.forEach((col, index) => {
        const isMandatory = mandatoryFields.includes(col);
        html += `
            <tr>
                <td>${index + 1}</td>
                <td><strong>${col}</strong> ${isMandatory ? '<span class="text-danger">*</span>' : ''}</td>
                <td><i class="bi bi-arrow-right text-primary"></i></td>
                <td>
                    <select class="form-select form-select-sm target-select" data-source="${col}">
                        <option value="">— ignore —</option>
                        ${targetColumns.map(tc => `<option value="${tc}">${tc}</option>`).join('')}
                    </select>
                </td>
                <td>
                    ${isMandatory ? '<span class="badge bg-danger">Required</span>' : '<span class="badge bg-secondary">Optional</span>'}
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;

    // Add change listeners to update mapping status
    document.querySelectorAll('.target-select').forEach(select => {
        select.addEventListener('change', function () {
            const source = this.dataset.source;
            const target = this.value;
            if (target) {
                currentMappings[source] = target;
            } else {
                delete currentMappings[source];
            }
            updateMappingStatus();
        });
    });

    // Show mandatory fields summary
    showMandatorySummary();

    updateMappingStatus();
}

// ===== Show Mandatory Fields Summary =====
function showMandatorySummary() {
    const summaryDiv = document.getElementById('mandatorySummary');
    const listSpan = document.getElementById('mandatoryList');

    // Get mandatory fields that exist in the file
    const fileMandatory = mandatoryFields.filter(f => parsedColumns.includes(f));

    if (fileMandatory.length) {
        summaryDiv.style.display = 'block';
        listSpan.innerHTML = fileMandatory.map(f => `<span class="badge bg-danger me-1">${f}</span>`).join('');
    } else {
        summaryDiv.style.display = 'none';
    }
}

// ===== Update Mapping Status =====
function updateMappingStatus() {
    const statusBadge = document.getElementById('mappingStatus');
    const saveBtn = document.getElementById('saveBtn');

    const totalMapped = Object.keys(currentMappings).length;
    const totalColumns = parsedColumns.length;

    // Check if all mandatory fields are mapped
    const fileMandatory = mandatoryFields.filter(f => parsedColumns.includes(f));
    const mandatoryMapped = fileMandatory.every(f => currentMappings[f] && currentMappings[f] !== '');

    const allMapped = fileMandatory.every(f => currentMappings[f] && currentMappings[f] !== '');
    const canSave = allMapped && totalMapped > 0;

    statusBadge.textContent = `${totalMapped}/${totalColumns} mapped`;
    statusBadge.className = `badge ${canSave ? 'bg-success' : 'bg-warning text-dark'}`;

    saveBtn.disabled = !canSave;
}

// ===== Save Mappings =====
async function saveMappings() {
    const supplierName = document.getElementById('supplierName').value.trim();
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('saveStatus');

    // Validate supplier name
    if (!supplierName) {
        showToast('Error', 'Please enter a supplier name', 'danger');
        document.getElementById('supplierName').focus();
        return;
    }

    // Check if supplier already exists
    if (supplierExists) {
        showToast('Error', 'Supplier name already exists. Please choose a different name.', 'danger');
        return;
    }

    // Validate mappings
    const fileMandatory = mandatoryFields.filter(f => parsedColumns.includes(f));
    const missingMandatory = fileMandatory.filter(f => !currentMappings[f] || currentMappings[f] === '');

    if (missingMandatory.length) {
        showToast('Error', `Missing required fields: ${missingMandatory.join(', ')}`, 'danger');
        return;
    }

    // Save
    saveBtn.disabled = true;
    statusDiv.innerHTML = '<span class="text-info">⏳ Saving mappings...</span>';

    try {
        // Save each mapping
        for (const [source, target] of Object.entries(currentMappings)) {
            const formData = new FormData();
            formData.append('source_field', source);
            formData.append('target_field', target);
            formData.append('active', 'true');

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

        // Redirect after 2 seconds
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
            // Supplier exists if there is at least one mapping
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
            // If the endpoint fails (e.g., 404), assume it's available
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
            feedback.textContent = '✅ Name is available';
            supplierExists = false;
        }
    } catch (e) {
        // Network error – assume available (or show warning)
        input.classList.remove('is-invalid');
        input.classList.remove('is-valid');
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
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', async function () {
    await fetchTargetSchema();

    // Supplier name validation on input
    document.getElementById('supplierName').addEventListener('input', checkSupplierName);

    // Enter key on supplier name triggers file upload
    document.getElementById('supplierName').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('parseFileBtn').click();
        }
    });

    // Enter key on file input triggers parse
    document.getElementById('sampleFile').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('parseFileBtn').click();
        }
    });

    // Auto-parse when file is selected
    document.getElementById('sampleFile').addEventListener('change', function () {
        if (this.files.length) {
            document.getElementById('parseFileBtn').click();
        }
    });
});