// ============================================================
// RENDER MAPPING UI
// ============================================================

function renderMappingUI() {
    console.log('✅ renderMappingUI called');
    const tbody = document.getElementById('mappingTableBody');
    if (!tbody) {
        console.error('❌ mappingTableBody not found');
        return;
    }

    const data = getPageData();
    console.log('📦 Page data:', data);
    if (!data) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Failed to load data</td></tr>`;
        return;
    }

    const { targetFields, sourceFields, supplierMappings, supplierId } = data;

    // Build initial mappings from backend data
    initialMappings = buildInitialMappings(supplierMappings, targetFields);
    console.log('📌 Initial mappings:', initialMappings);

    // Exclude ProductID
    const excludedColumns = ['ProductID'];
    const filteredTargets = targetFields.filter(col => !excludedColumns.includes(col.field_name));

    // Sort: mandatory first
    const sortedTargets = [...filteredTargets].sort((a, b) => {
        const aRequired = a.is_nullable === false;
        const bRequired = b.is_nullable === false;
        if (aRequired && !bRequired) return -1;
        if (!aRequired && bRequired) return 1;
        return 0;
    });

    // Reset currentMappings
    currentMappings = {};

    let html = '';
    sortedTargets.forEach((target, index) => {
        const targetName = target.field_name;
        const targetId = target.id;
        const isNullable = target.is_nullable;
        const isMandatory = isNullable === false;
        const mapping = supplierMappings[targetName] || {};
        const hasSource = mapping.source_field || null;
        const isMandatoryChecked = mapping.is_mandatory || false;
        const prepopulatedValue = mapping.prepopulated_value || '';

        // Store initial state
        currentMappings[targetName] = {
            source_field: hasSource,
            is_mandatory: isMandatoryChecked,
            prepopulated_value: prepopulatedValue
        };

        html += `
            <tr>
                <td>${index + 1}</td>
                <td>
                    <strong>${targetName}</strong>
                    ${isMandatory ? '<span class="text-danger">*</span>' : ''}
                    <br><span class="text-muted small">${target.data_type || ''}</span>
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
                           ${isMandatoryChecked ? 'checked' : ''}
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

    if (sortedTargets.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted py-4">
                    No fields available for mapping after excluding: ${excludedColumns.join(', ')}
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = html;

    // Update mandatory summary
    updateMandatorySummary();

    // Attach event listeners
    attachEventListeners();

    // Reset dirty state
    hasChanges = false;
    updateSaveButton();

    console.log('✅ renderMappingUI completed');
}