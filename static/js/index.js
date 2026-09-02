// ===== Toggle New Supplier Input =====
document.addEventListener('DOMContentLoaded', function () {
  const supplierSelect = document.getElementById('supplierInput');
  const newSupplierInput = document.getElementById('newSupplierInput');

  supplierSelect.addEventListener('change', function () {
    if (this.value === '__new__') {
      newSupplierInput.style.display = 'inline-block';
      newSupplierInput.focus();
    } else {
      newSupplierInput.style.display = 'none';
      newSupplierInput.value = '';
    }
  });

  // Handle Enter key on new supplier input
  newSupplierInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      uploadFile();
    }
  });
});

// ===== Upload File =====
async function uploadFile() {
  const fileInput = document.getElementById('fileInput');
  const supplierSelect = document.getElementById('supplierInput');
  const newSupplierInput = document.getElementById('newSupplierInput');
  const dryRun = document.getElementById('dryRunInput').checked;
  const resultDiv = document.getElementById('result');

  if (!fileInput.files.length) {
    resultDiv.innerHTML = '<div class="error">❌ Please select a file</div>';
    return;
  }

  // Determine supplier name
  let supplier = supplierSelect.value;
  if (supplier === '__new__') {
    supplier = newSupplierInput.value.trim();
    if (!supplier) {
      resultDiv.innerHTML = '<div class="error">❌ Please enter a supplier name</div>';
      return;
    }
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('supplier', supplier);
  formData.append('dry_run', dryRun);
  formData.append('batch_size', 1000);

  resultDiv.innerHTML = '<div class="info">⏳ Uploading...</div>';

  try {
    const response = await fetch('/upload', { method: 'POST', body: formData });
    const data = await response.json();

    if (response.ok) {
      let html = '<div class="success">✅ Import completed successfully!</div>';
      html += `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      resultDiv.innerHTML = html;

      // If it was a new supplier, refresh dropdown
      if (supplierSelect.value === '__new__') {
        await refreshSuppliersDropdown();
      }

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
  }
}

// ===== Clear Result =====
function clearResult() {
  document.getElementById('result').innerHTML = '<p class="text-muted">Ready to import...</p>';
  document.getElementById('fileInput').value = '';
  document.getElementById('newMappingInput').value = '';
  document.getElementById('newMappingInput').style.display = 'none';
  document.getElementById('mappingInput').value = 'default';
}