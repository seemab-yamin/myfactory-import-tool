// ===== Save Mappings (using shared utils) =====
async function saveMappings() {
    const supplierName = document.getElementById('supplierName').value.trim();
    const statusDiv = document.getElementById('saveStatus');
    const saveBtn = document.getElementById('saveBtn');

    if (!supplierName) {
        showToast('Error', 'Please enter a supplier name', 'danger');
        document.getElementById('supplierName').focus();
        return;
    }

    if (supplierExists) {
        showToast('Error', 'Supplier name already exists. Please choose a different name.', 'danger');
        return;
    }

    // Step 1: Collect current state from UI
    const currentState = collectMappingsFromUI();

    // Step 2: For new supplier, initial state is empty
    const emptyState = {};
    Object.keys(currentState).forEach(key => {
        emptyState[key] = { source_field: null, is_mandatory: false, prepopulated_value: '' };
    });

    // Step 3: Detect changes (everything is new)
    const changes = detectChanges(currentState, emptyState);

    // Step 4: Separate updates and deletions (no deletions for new supplier)
    const toUpdate = changes.filter(c => c.source_field || c.prepopulated_value);
    const toDelete = [];

    // For prepopulated-only mappings, set unique source_field
    toUpdate.forEach(c => {
        if ((!c.source_field || c.source_field.trim() === '') && c.prepopulated_value) {
            c.source_field = `None`;
        }
    });

    // Step 5: Validate
    const errors = validateMappings(toUpdate);
    if (errors.length > 0) {
        highlightErrorRows(errors);
        renderValidationErrors(statusDiv, errors);
        showToast('Validation Error', `${errors.length} error(s) found.`, 'danger');
        scrollToFirstError();
        return;
    }

    if (toUpdate.length === 0) {
        statusDiv.innerHTML = '<span class="text-warning">⚠️ No mappings to save.</span>';
        showToast('Warning', 'No mappings to save.', 'warning');
        return;
    }

    saveBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-info">⏳ Saving ${toUpdate.length} mapping(s)...</span>`;

    // Step 6: Save via API
    const results = await saveMappingsWithAPI(supplierName, toUpdate, toDelete, {
        onSuccess: async (res) => {
            renderSaveResults(statusDiv, res);
            showToast('Success', `All ${res.successCount} mappings saved successfully!`, 'success');
            await fetchAllSuppliers();
            // Get supplier ID from first successful response
            // Note: You may need to store supplier_id during creation
            setTimeout(() => {
                window.location.href = `/show-mapping/${encodeURIComponent(window.supplierId || supplierName)}`;
            }, 1500);
        },
        onError: (res) => {
            renderSaveResults(statusDiv, res);
            showToast('Partial Save', `${res.successCount} succeeded, ${res.failureCount} failed.`, 'warning');
            saveBtn.disabled = false;
        }
    });
}