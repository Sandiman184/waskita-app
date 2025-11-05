/**
 * Waskita Application - Main JavaScript File
 * Provides common functionality across the application
 */

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    
    
    // Initialize all components
    initializeFlashMessages();
    initializeFormValidation();
    initializeDataTables();
    initializeTooltips();
    initializeConfirmDialogs();
});

/**
 * Flash Messages Handler
 */
function initializeFlashMessages() {
    const flashMessages = document.querySelectorAll('.alert');
    
    flashMessages.forEach(function(message) {
        // Auto-hide success messages after 5 seconds
        if (message.classList.contains('alert-success')) {
            setTimeout(function() {
                message.style.opacity = '0';
                setTimeout(function() {
                    message.remove();
                }, 300);
            }, 5000);
        }
        
        // Add close button functionality
        const closeBtn = message.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                message.style.opacity = '0';
                setTimeout(function() {
                    message.remove();
                }, 300);
            });
        }
    });
}

/**
 * Form Validation
 */
function initializeFormValidation() {
    const forms = document.querySelectorAll('form[data-validate="true"]');
    
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!validateForm(form)) {
                e.preventDefault();
                return false;
            }
        });
    });
}

function validateForm(form) {
    let isValid = true;
    const requiredFields = form.querySelectorAll('[required]');
    
    requiredFields.forEach(function(field) {
        if (!field.value.trim()) {
            showFieldError(field, 'Field ini wajib diisi');
            isValid = false;
        } else {
            clearFieldError(field);
        }
    });
    
    // Email validation
    const emailFields = form.querySelectorAll('input[type="email"]');
    emailFields.forEach(function(field) {
        if (field.value && !isValidEmail(field.value)) {
            showFieldError(field, 'Format email tidak valid');
            isValid = false;
        }
    });
    
    return isValid;
}

function showFieldError(field, message) {
    clearFieldError(field);
    
    field.classList.add('is-invalid');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    field.parentNode.appendChild(errorDiv);
}

function clearFieldError(field) {
    field.classList.remove('is-invalid');
    const errorDiv = field.parentNode.querySelector('.invalid-feedback');
    if (errorDiv) {
        errorDiv.remove();
    }
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * DataTables Initialization
 */
function initializeDataTables() {
    const tables = document.querySelectorAll('.data-table');
    
    tables.forEach(function(table) {
        if (typeof DataTable !== 'undefined') {
            new DataTable(table, {
                pageLength: 25,
                responsive: true,
                language: {
                    url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/id.json'
                }
            });
        }
    });
}

/**
 * Bootstrap Tooltips
 */
function initializeTooltips() {
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

/**
 * Confirmation Dialogs
 */
function initializeConfirmDialogs() {
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    
    confirmButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            const message = button.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
}

/**
 * Loading Spinner Utilities
 */
function showLoading(element) {
    if (element) {
        element.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading...';
        element.disabled = true;
    }
}

function hideLoading(element, originalText) {
    if (element) {
        element.innerHTML = originalText || 'Submit';
        element.disabled = false;
    }
}

/**
 * AJAX Helper Functions
 */
function makeAjaxRequest(url, options = {}) {
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    };
    
    const finalOptions = { ...defaultOptions, ...options };
    
    return fetch(url, finalOptions)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .catch(error => {
            console.error('AJAX Error:', error);
            throw error;
        });
}

/**
 * Classification Page Specific Functions
 */
function initializeClassificationPage() {
    const classifyButtons = document.querySelectorAll('.btn-classify');
    
    classifyButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const dataId = button.getAttribute('data-id');
            const dataType = button.getAttribute('data-type');
            
            if (dataId && dataType) {
                classifyData(dataId, dataType, button);
            }
        });
    });
}

function showManualClassification() {
    // Redirect to manual classification page
    window.location.href = '/classification/classify?type=manual';
}

function classifyData(dataId, dataType, button) {
    const originalText = button.innerHTML;
    showLoading(button);
    
    makeAjaxRequest(`/api/classify_data`, {
        method: 'POST',
        body: JSON.stringify({
            data_id: dataId,
            data_type: dataType
        })
    })
    .then(data => {
        if (data.success) {
            button.innerHTML = '<i class="fas fa-check"></i> Classified';
            button.classList.remove('btn-primary');
            button.classList.add('btn-success');
            button.disabled = true;
            
            // Update the result display if exists
            const resultElement = document.querySelector(`#result-${dataId}`);
            if (resultElement && data.result) {
                resultElement.innerHTML = `
                    <span class="badge bg-${data.result.sentiment === 'positive' ? 'success' : 
                                            data.result.sentiment === 'negative' ? 'danger' : 'warning'}">
                        ${data.result.sentiment}
                    </span>
                    <small class="text-muted">(${(data.result.confidence * 100).toFixed(1)}%)</small>
                `;
            }
        } else {
            throw new Error(data.message || 'Classification failed');
        }
    })
    .catch(error => {
        console.error('Classification error:', error);
        alert('Terjadi kesalahan saat melakukan klasifikasi: ' + error.message);
        hideLoading(button, originalText);
    });
}

/**
 * Registration Page Functions
 */
function initializeRegistrationPage() {
    const registrationForm = document.querySelector('#registrationForm');
    
    if (registrationForm) {
        registrationForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitRegistrationRequest();
        });
    }
}

function submitRegistrationRequest() {
    const form = document.querySelector('#registrationForm');
    const submitButton = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);
    
    showLoading(submitButton);
    
    fetch('/otp/register-request', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = data.redirect_url;
        } else {
            throw new Error(data.message || 'Registration failed');
        }
    })
    .catch(error => {
        console.error('Registration error:', error);
        alert('Terjadi kesalahan: ' + error.message);
        hideLoading(submitButton, 'Kirim Permintaan');
    });
}

/**
 * Export functions for global use
 */
window.WaskitaApp = {
    showLoading,
    hideLoading,
    makeAjaxRequest,
    classifyData,
    validateForm,
    initializeClassificationPage,
    initializeRegistrationPage
};