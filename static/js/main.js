// ===== Connection Check =====
async function checkConnection() {
    const statusDiv = document.getElementById('connectionStatus');
    if (!statusDiv) return;
    try {
        const resp = await fetch('/health');
        const data = await resp.json();
        if (data.configured) {
            statusDiv.innerHTML = '<span style="color: green;">✅ Connected to database</span>';
        } else {
            statusDiv.innerHTML = '<span style="color: orange;">⚠️ Database not configured. Run setup first.</span>';
        }
    } catch {
        statusDiv.innerHTML = '<span style="color: red;">❌ Cannot connect to API server</span>';
    }
}

// ===== Toast Notification =====
function showToast(title, message, type = 'info') {
    const container = document.querySelector('.toast-container') || (() => {
        const el = document.createElement('div');
        el.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(el);
        return el;
    })();

    const colors = {
        success: 'bg-success',
        danger: 'bg-danger',
        info: 'bg-info',
        warning: 'bg-warning'
    };

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white border-0 ${colors[type] || 'bg-secondary'}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body"><strong>${title}</strong> — ${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

// Auto-check connection on pages that have #connectionStatus
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('connectionStatus')) {
        checkConnection();
    }
});