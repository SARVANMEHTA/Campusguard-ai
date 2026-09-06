/**
 * CampusGuard AI - Interactive Frontend Controller
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-refresh queues if enabled on dashboard
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    if (autoRefreshToggle) {
        setInterval(() => {
            if (autoRefreshToggle.checked) {
                checkQueueUpdates();
            }
        }, 8000);
    }
});

/**
 * Polls API for new pending review items and updates badge counts.
 */
async function checkQueueUpdates() {
    try {
        const response = await fetch('/api/stats/');
        if (!response.ok) return;
        const data = await response.json();

        // Update badge counts in navigation
        const highBadge = document.getElementById('highQueueBadge');
        if (highBadge) {
            highBadge.innerText = data.high_confidence_pending;
            highBadge.style.display = data.high_confidence_pending > 0 ? 'inline-block' : 'none';
        }

        const lowBadge = document.getElementById('lowQueueBadge');
        if (lowBadge) {
            lowBadge.innerText = data.low_confidence_pending;
            lowBadge.style.display = data.low_confidence_pending > 0 ? 'inline-block' : 'none';
        }
    } catch (err) {
        console.warn('Queue update poll error:', err);
    }
}

/**
 * Fast 1-click verification via AJAX with feedback.
 */
async function quickVerifyDetection(detectionId, studentName) {
    if (!confirm(`Are you sure you want to officially VERIFY that the detected person is ${studentName} and DISPATCH an email alert to security authorities?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/detections/${detectionId}/verify/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ notes: 'Verified via 1-click review action by admin.' })
        });

        const result = await response.json();
        if (result.success) {
            showToast('Alert Dispatched!', `Verification confirmed for ${studentName}. Email sent to security.`, 'success');
            setTimeout(() => window.location.reload(), 1200);
        } else {
            showToast('Error', result.error || 'Failed to verify detection.', 'danger');
        }
    } catch (err) {
        showToast('Network Error', err.message, 'danger');
    }
}

/**
 * Fast 1-click rejection via AJAX.
 */
async function quickRejectDetection(detectionId, studentName) {
    if (!confirm(`Mark detection for ${studentName} as FALSE POSITIVE / REJECTED?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/detections/${detectionId}/reject/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ notes: 'Marked as false positive by admin.' })
        });

        const result = await response.json();
        if (result.success) {
            showToast('Marked as Rejected', `Detection #${detectionId} marked as False Positive.`, 'info');
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showToast('Error', result.error || 'Failed to reject detection.', 'danger');
        }
    } catch (err) {
        showToast('Network Error', err.message, 'danger');
    }
}

/**
 * Helper to display dynamic Bootstrap Toast notifications.
 */
function showToast(title, message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    const toastId = 'toast_' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : type === 'danger' ? 'bg-danger' : 'bg-primary';

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0 mb-2" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <strong>${title}</strong><br>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastEl = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
    toast.show();
}

/**
 * Retrieves CSRF cookie token for AJAX POST requests.
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
