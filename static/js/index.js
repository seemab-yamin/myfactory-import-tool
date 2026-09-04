// ============================================================
// HOME PAGE – IMPORT UI
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
  const supplierSelect = document.getElementById('supplierInput');
  const fileInput = document.getElementById('fileInput');
  const importBtn = document.getElementById('importBtn');

  // ===== Enable/Disable Import Button =====
  function updateImportButton() {
    const hasSupplier = supplierSelect.value && supplierSelect.value !== '';
    const hasFile = fileInput.files && fileInput.files.length > 0;
    importBtn.disabled = !(hasSupplier && hasFile);
  }

  // ===== Event Listeners =====
  supplierSelect.addEventListener('change', updateImportButton);
  fileInput.addEventListener('change', updateImportButton);

  // Initial state
  updateImportButton();
});

// ===== Upload File =====
async function uploadFile() {
  const fileInput = document.getElementById('fileInput');
  const supplierSelect = document.getElementById('supplierInput');
  const dryRun = document.getElementById('dryRunInput').checked;
  const resultDiv = document.getElementById('result');
  const importBtn = document.getElementById('importBtn');

  // Validate
  if (!fileInput.files.length) {
    resultDiv.innerHTML = '<div class="error">❌ Please select a file</div>';
    return;
  }

  const supplierId = supplierSelect.value;
  if (!supplierId) {
    resultDiv.innerHTML = '<div class="error">❌ Please select a supplier</div>';
    return;
  }

  // Build FormData
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('supplier', supplierId);
  formData.append('dry_run', dryRun);
  formData.append('batch_size', 1000);

  // Disable button during upload
  importBtn.disabled = true;
  importBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Uploading...';
  resultDiv.innerHTML = '<div class="info">⏳ Uploading...</div>';

  try {
    const response = await fetch('/upload', { method: 'POST', body: formData });
    const data = await response.json();

    if (response.ok) {
      let html = '<div class="success">✅ Import completed successfully!</div>';
      html += `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      resultDiv.innerHTML = html;

      if (data.preview && data.preview.length) {
        resultDiv.innerHTML += `<h5>Preview Data:</h5><pre>${JSON.stringify(data.preview, null, 2)}</pre>`;
      }
    } else {
      let errorMsg = data.detail || 'Unknown error';
      if (typeof errorMsg === 'object') errorMsg = JSON.stringify(errorMsg, null, 2);
      resultDiv.innerHTML = `<div class="error">❌ Error: ${errorMsg}</div>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<div class="error">❌ Network Error: ${e.message}</div>`;
  } finally {
    // Restore button state
    importBtn.disabled = false;
    importBtn.innerHTML = '<i class="bi bi-upload"></i> Upload & Import';
  }
}

// ===== Clear Result =====
function clearResult() {
  document.getElementById('result').innerHTML = '<p class="text-muted">Ready to import...</p>';
  document.getElementById('fileInput').value = '';
  // Trigger change event to re-evaluate button state
  const event = new Event('change');
  document.getElementById('fileInput').dispatchEvent(event);
}