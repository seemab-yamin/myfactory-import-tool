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

  // ===== File Selection Handler =====
  async function handleFileSelect() {
    const file = fileInput.files[0];
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileStatus = document.getElementById('fileStatus');
    const previewContainer = document.getElementById('previewContainer');

    // Clear previous preview
    previewContainer.style.display = 'none';

    if (!file) {
      fileInfo.style.display = 'none';
      updateImportButton();
      return;
    }

    // ✅ Validate file extension
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

    // ✅ Show file info
    fileInfo.style.display = 'block';
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileStatus.textContent = '⏳ Parsing...';
    fileStatus.className = 'badge bg-warning text-dark ms-1';

    // ✅ Parse file via backend
    try {
      const supplier = supplierSelect.value;
      if (!supplier) {
        fileStatus.textContent = '⚠️ Select supplier first';
        fileStatus.className = 'badge bg-warning text-dark ms-1';
        return;
      }

      const formData = new FormData();
      formData.append('file', file);
      formData.append('supplier_name', supplier);

      const response = await fetch('/api/parse-sample', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to parse file');
      }

      const data = await response.json();

      // ✅ Update status
      fileStatus.textContent = '✅ Parsed';
      fileStatus.className = 'badge bg-success ms-1';

      // ✅ Render preview
      renderPreview(data);

      // ✅ Update import button
      updateImportButton();

    } catch (e) {
      console.error('Parse error:', e);
      fileStatus.textContent = '❌ ' + e.message;
      fileStatus.className = 'badge bg-danger ms-1';
      importBtn.disabled = true;
    }
  }

  // ===== Render Preview Table =====
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

    // ✅ Build header
    head.innerHTML = `<tr>${columns.map(col => `<th>${col}</th>`).join('')}</tr>`;

    // ✅ Build body (first 5 rows)
    body.innerHTML = preview.slice(0, 5).map(row => `
      <tr>${columns.map(col => `<td>${row[col] !== null && row[col] !== undefined ? row[col] : ''}</td>`).join('')}</tr>
    `).join('');

    // ✅ Show stats
    stats.textContent = `${data.row_count || 0} rows, ${data.column_count || 0} columns`;
    previewContainer.style.display = 'block';
  }

  // ===== Format File Size =====
  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  // ===== Event Listeners =====
  supplierSelect.addEventListener('change', function () {
    // If file is already selected, re-parse with new supplier
    if (fileInput.files.length > 0) {
      handleFileSelect();
    }
    updateImportButton();
  });

  fileInput.addEventListener('change', function () {
    // Clear previous result
    clearResult();
    if (this.files.length > 0) {
      handleFileSelect();
    } else {
      document.getElementById('fileInfo').style.display = 'none';
      document.getElementById('previewContainer').style.display = 'none';
      updateImportButton();
    }
  });

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
  // Don't clear file input, only the result display
}