// ============================================================
// HOME PAGE – IMPORT UI
// ============================================================

// ============================================================
// HELPERS
// ============================================================

function getSelectedSupplierConfig() {
  const sel = document.getElementById('supplierInput');
  if (!sel) return null;

  const opt = sel.options[sel.selectedIndex];
  if (!opt || !opt.value) return null;

  return {
    supplierId: opt.dataset.supplierId || opt.value,
    supplierName: opt.dataset.supplierName || opt.textContent.trim(),
    headerRowIndex: opt.dataset.headerRowIndex ?? '1',
    sheetName: opt.dataset.sheetName ?? '',
    delimiter: opt.dataset.delimiter ?? ',',
  };
}

function renderSupplierConfigHint() {
  const hint = document.getElementById('supplierConfigHint');
  if (!hint) return;

  const cfg = getSelectedSupplierConfig();
  if (!cfg) {
    hint.innerHTML = '';
    hint.style.display = 'none';
    return;
  }

  const bits = [];
  bits.push(`<span class="badge bg-secondary">Header row: ${cfg.headerRowIndex}</span>`);
  if (cfg.sheetName) {
    bits.push(`<span class="badge bg-info text-dark">Sheet: ${cfg.sheetName}</span>`);
  }
  bits.push(`<span class="badge bg-light text-dark border">Delimiter: <code>${cfg.delimiter}</code></span>`);

  hint.innerHTML = bits.join(' ');
  hint.style.display = 'block';
}

// ============================================================
// DOMContentLoaded
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

  // ✅ Gate the file input on supplier selection
  function updateFileInputGate() {
    const hasSupplier = supplierSelect.value && supplierSelect.value !== '';
    fileInput.disabled = !hasSupplier;

    const fileGateHint = document.getElementById('fileGateHint');
    if (fileGateHint) {
      if (!hasSupplier) {
        fileGateHint.innerHTML =
          '<span class="text-muted small">⚠️ Select a supplier first to enable file upload</span>';
      } else {
        fileGateHint.innerHTML = '';
      }
    }
  }

  // ===== File Selection Handler =====
  async function handleFileSelect() {
    const file = fileInput.files[0];
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileStatus = document.getElementById('fileStatus');
    const previewContainer = document.getElementById('previewContainer');

    previewContainer.style.display = 'none';

    if (!file) {
      fileInfo.style.display = 'none';
      updateImportButton();
      return;
    }

    const validExtensions = ['.csv', '.xlsx', '.xls'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!validExtensions.includes(ext)) {
      fileInfo.style.display = 'block';
      fileName.textContent = file.name;
      fileSize.textContent = formatFileSize(file.size);
      fileStatus.textContent = '❌ Unsupported file type';
      fileStatus.className = 'badge bg-danger ms-1';
      importBtn.disabled = true;
      return;
    }

    fileInfo.style.display = 'block';
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileStatus.textContent = '⏳ Parsing...';
    fileStatus.className = 'badge bg-warning text-dark ms-1';

    const supplierCfg = getSelectedSupplierConfig();
    if (!supplierCfg) {
      fileStatus.textContent = '⚠️ Select supplier first';
      fileStatus.className = 'badge bg-warning text-dark ms-1';
      return;
    }

    console.log('[index] Parsing with supplier config:', supplierCfg);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('header_row_index', String(supplierCfg.headerRowIndex));

      if (supplierCfg.sheetName) {
        formData.append('sheet_name', supplierCfg.sheetName);
      }
      formData.append('delimiter', supplierCfg.delimiter || ',');

      const response = await fetch('/api/parse-sample', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();

      fileStatus.textContent = '✅ Parsed';
      fileStatus.className = 'badge bg-success ms-1';

      renderPreview(data);
      updateImportButton();

    } catch (e) {
      console.error('Parse error:', e);
      fileStatus.textContent = '❌ ' + e.message;
      fileStatus.className = 'badge bg-danger ms-1';
      importBtn.disabled = true;
    }
  }

  function renderPreview(data) {
    const previewContainer = document.getElementById('previewContainer');
    const head = document.getElementById('previewHead');
    const body = document.getElementById('previewBody');
    const stats = document.getElementById('previewStats');

    const columns = data.columns || [];
    const preview = data.preview || [];

    if (!columns.length || !preview.length) {
      previewContainer.style.display = 'none';
      return;
    }

    head.innerHTML = `<tr>${columns.map(col => `<th>${col}</th>`).join('')}</tr>`;

    body.innerHTML = preview.slice(0, 5).map(row => `
            <tr>${columns.map(col => `<td>${row[col] !== null && row[col] !== undefined ? row[col] : ''}</td>`).join('')}</tr>
        `).join('');

    stats.textContent = `${data.row_count || 0} rows, ${data.column_count || 0} columns`;
    previewContainer.style.display = 'block';
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  // ===== Event Listeners =====
  supplierSelect.addEventListener('change', function () {
    // ✅ Toggle file input gate
    updateFileInputGate();

    // Update config hint
    renderSupplierConfigHint();

    // If a file was already selected, re-parse with new supplier config
    if (fileInput.files.length > 0) {
      handleFileSelect();
    }
    updateImportButton();
  });

  fileInput.addEventListener('change', function () {
    clearResult();
    if (this.files.length > 0) {
      handleFileSelect();
    } else {
      document.getElementById('fileInfo').style.display = 'none';
      document.getElementById('previewContainer').style.display = 'none';
      updateImportButton();
    }
  });

  // ✅ Initial state on page load
  updateFileInputGate();
  renderSupplierConfigHint();
  updateImportButton();
});

// ============================================================
// UPLOAD FILE
// ============================================================
async function uploadFile() {
  const fileInput = document.getElementById('fileInput');
  const supplierSelect = document.getElementById('supplierInput');
  const dryRun = document.getElementById('dryRunInput').checked;
  const batchSize = document.getElementById('batchSizeInput').value;
  const resultDiv = document.getElementById('result');
  const importBtn = document.getElementById('importBtn');

  if (!fileInput.files.length) {
    resultDiv.innerHTML = '<div class="error">❌ Please select a file</div>';
    return;
  }

  const supplierId = supplierSelect.value;
  if (!supplierId) {
    resultDiv.innerHTML = '<div class="error">❌ Please select a supplier</div>';
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('supplier_id', supplierId);
  formData.append('dry_run', dryRun);
  formData.append('batch_size', batchSize);

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
    importBtn.disabled = false;
    importBtn.innerHTML = '<i class="bi bi-upload"></i> Upload & Import';
  }
}

// ===== Clear Result =====
function clearResult() {
  const result = document.getElementById('result');
  if (result) {
    result.innerHTML = '<p class="text-muted">Ready to import...</p>';
  }
}