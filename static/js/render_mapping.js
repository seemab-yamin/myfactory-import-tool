// ============================================================
// RENDER MAPPING UI
// ============================================================

function renderMappingUI() {
    const tbody = document.getElementById('mappingTableBody');
    if (!tbody) {
        console.error('❌ mappingTableBody not found');
        return;
    }

    const data = getPageData();
    console.log('📦 Page data:', data);
    if (!data) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Failed to load data</td></tr>`;
        return;
    }

    const { supplierId, supplierName, sourceFields, supplierMappings } = data;

    // ✅ supplierMappings is a list of mapping objects
    // Each mapping has: target_field_id, target_field_name, source_field, is_mandatory, prepopulated_value
    const mappingsList = supplierMappings || [];

    console.log('📌 Mappings list:', mappingsList);
    console.log('📌 Source fields:', sourceFields);

    if (mappingsList.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-muted py-4">
                    No mappings found for this supplier.
                </td>
            </tr>
        `;
        return;
    }

    // Reset currentMappings
    currentMappings = {};
    initialMappings = {};

    let html = '';
    mappingsList.forEach((mapping, index) => {
        const targetId = mapping.target_field_id;
        const targetName = mapping.target_field_name || `Field_${targetId}`;
        const hasSource = mapping.source_field || null;
        const isMandatory = mapping.is_mandatory || false;
        const prepopulatedValue = mapping.prepopulated_value || '';
        const dataType = mapping.data_type || '';

        // Store current state for change detection
        currentMappings[targetName] = {
            source_field: hasSource,
            is_mandatory: isMandatory,
            prepopulated_value: prepopulatedValue,
            target_id: targetId
        };

        // Also store initial state for change detection
        initialMappings[targetName] = {
            source_field: hasSource,
            is_mandatory: isMandatory,
            prepopulated_value: prepopulatedValue,
            target_id: targetId
        };

        html += `
            <tr>
                <td>${index + 1}</td>
                <td>
                    <strong>${targetName}</strong>
                    ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                    <br><span class="text-muted small">${dataType}</span>
                    <br><span class="text-muted small">ID: ${targetId}</span>
                </td>
                <td>
                    <select class="form-select form-select-sm source-select" data-target-id="${targetId}" data-target-name="${targetName}">
                        <option value="None">None</option>
                        ${sourceFields.map(sf => `
                            <option value="${sf}" ${hasSource === sf ? 'selected' : ''}>
                                ${sf}
                            </option>
                        `).join('')}
                    </select>
                </td>
                <td class="text-center">
                    <input type="checkbox" class="form-check-input mandatory-check" 
                           data-target-id="${targetId}"
                           ${isMandatory ? 'checked' : ''}
                           ${isMandatory ? 'disabled' : ''}>
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm prepopulated-value" 
                           data-target-id="${targetId}"
                           value="${prepopulatedValue}"
                           placeholder="Pre Populated value...">
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;

    // Update mandatory summary
    updateMandatorySummary();

    // Attach event listeners
    attachEventListeners();

    // Reset dirty state
    hasChanges = false;
    updateSaveButton();
}