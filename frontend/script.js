// Toast notification helper function
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    const toastTitle = document.getElementById('toast-title');
    
    // Set message
    toastMessage.textContent = message;
    
    // Set title and styling based on type
    const toastElement = bootstrap.Toast.getOrCreateInstance(toast);
    toast.className = 'toast';
    
    if (type === 'success') {
        toastTitle.textContent = 'Success';
        toast.classList.add('text-bg-success');
    } else if (type === 'error') {
        toastTitle.textContent = 'Error';
        toast.classList.add('text-bg-danger');
    } else if (type === 'warning') {
        toastTitle.textContent = 'Warning';
        toast.classList.add('text-bg-warning');
    } else {
        toastTitle.textContent = 'Info';
        toast.classList.add('text-bg-info');
    }
    
    toastElement.show();
}

document.addEventListener('DOMContentLoaded', () => {
    // Pre-fill the host_url with the current location
    const hostUrlInput = document.getElementById('host_url');
    if (hostUrlInput) {
        hostUrlInput.value = window.location.origin;
    }
    
    // Auto-detect and set timezone
    const timezoneSelect = document.getElementById('timezone');
    if (timezoneSelect) {
        // Get browser's timezone
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        // Populate common timezones
        const commonTimezones = [
            { value: 'America/New_York', label: 'Eastern Time (US)' },
            { value: 'America/Chicago', label: 'Central Time (US)' },
            { value: 'America/Denver', label: 'Mountain Time (US)' },
            { value: 'America/Los_Angeles', label: 'Pacific Time (US)' },
            { value: 'America/Toronto', label: 'Eastern Time (Canada)' },
            { value: 'America/Vancouver', label: 'Pacific Time (Canada)' },
            { value: 'Europe/London', label: 'London' },
            { value: 'Europe/Paris', label: 'Paris' },
            { value: 'Europe/Berlin', label: 'Berlin' },
            { value: 'Europe/Rome', label: 'Rome' },
            { value: 'Europe/Madrid', label: 'Madrid' },
            { value: 'Asia/Tokyo', label: 'Tokyo' },
            { value: 'Asia/Shanghai', label: 'Shanghai' },
            { value: 'Asia/Dubai', label: 'Dubai' },
            { value: 'Australia/Sydney', label: 'Sydney' },
            { value: 'Australia/Melbourne', label: 'Melbourne' },
            { value: 'UTC', label: 'UTC' }
        ];
        
        // Add common timezones to select
        commonTimezones.forEach(tz => {
            const option = document.createElement('option');
            option.value = tz.value;
            option.textContent = tz.label;
            if (tz.value === browserTimezone) {
                option.selected = true;
            }
            timezoneSelect.appendChild(option);
        });
        
        // If browser timezone is not in common list, add it
        if (!commonTimezones.find(tz => tz.value === browserTimezone)) {
            const option = document.createElement('option');
            option.value = browserTimezone;
            option.textContent = `${browserTimezone} (detected)`;
            option.selected = true;
            timezoneSelect.insertBefore(option, timezoneSelect.firstChild.nextSibling);
        }
        
        // Set the detected timezone as default if no value is set
        if (!timezoneSelect.value && browserTimezone) {
            timezoneSelect.value = browserTimezone;
        }
    }

    if (navigator.share) {
        document.getElementById('shareBtn').style.display = 'inline-block';
    } else {
        document.getElementById('copyBtn').style.display = 'inline-block';
    }

    // Mode toggle handlers
    const modeNew = document.getElementById('mode-new');
    const modeUpdate = document.getElementById('mode-update');
    const secretStrGroup = document.getElementById('secret-str-group');
    const secretStrInput = document.getElementById('secret_str');
    const submitBtn = document.getElementById('submit-btn');
    const submitBtnText = document.getElementById('submit-btn-text');
    const loadConfigBtn = document.getElementById('load-config-btn');

    // Check if we're on a /{secret_str}/configure URL and auto-load configuration
    // Do this AFTER event listeners are set up
    const pathMatch = window.location.pathname.match(/^\/([^\/]+)\/configure$/);
    if (pathMatch) {
        const secretStr = pathMatch[1];
        // Wait a bit for all event listeners to be set up, then switch to update mode
        setTimeout(() => {
            // Switch to update mode
            modeUpdate.checked = true;
            modeUpdate.dispatchEvent(new Event('change'));
            
            // Set the secret_str after mode switch completes
            setTimeout(() => {
                secretStrInput.value = secretStr;
                
                // Auto-load the configuration
                // The loadConfigBtn click handler will show an error toast if the config doesn't exist
                if (loadConfigBtn) {
                    loadConfigBtn.click();
                }
            }, 100);
        }, 200);
    }

    modeNew.addEventListener('change', () => {
        if (modeNew.checked) {
            secretStrGroup.style.display = 'none';
            submitBtnText.textContent = 'Install in Stremio';
            clearForm();
        }
    });

    modeUpdate.addEventListener('change', () => {
        if (modeUpdate.checked) {
            secretStrGroup.style.display = 'block';
            submitBtnText.textContent = 'Update Configuration';
        }
    });

    // Load existing configuration
    loadConfigBtn.addEventListener('click', async () => {
        const secretStr = secretStrInput.value.trim();
        if (!secretStr) {
            showToast('Please enter your secret_str', 'warning');
            return;
        }

        loadConfigBtn.disabled = true;
        loadConfigBtn.textContent = 'Loading...';

        try {
            // First verify the secret_str exists by checking the config endpoint
            const configResponse = await fetch(`/${secretStr}/config`);
            if (!configResponse.ok) {
                if (configResponse.status === 404) {
                    throw new Error(`Configuration not found for this secret_str. Please check the URL or create a new configuration.`);
                } else if (configResponse.status === 400) {
                    throw new Error('Invalid secret_str format. Please check the URL.');
                } else if (configResponse.status === 503) {
                    throw new Error('Service temporarily unavailable. Please try again in a few moments.');
                } else {
                    throw new Error('Could not load configuration. Please try again.');
                }
            }

            const config = await configResponse.json();
            
            // Populate form fields
            document.getElementById('m3u_sources').value = config.m3u_sources.join('\n');
            document.getElementById('parser_schedule_crontab').value = config.parser_schedule_crontab;
            document.getElementById('host_url').value = config.host_url;
            // Password field should remain empty for security (has_password is just a boolean)
            document.getElementById('addon_password').value = '';
            // Set timezone if available
            if (config.timezone) {
                document.getElementById('timezone').value = config.timezone;
            }

            // Only show toast if not auto-loading (to avoid annoying popup on page load)
            const isAutoLoad = window.location.pathname.match(/^\/([^\/]+)\/configure$/);
            if (!isAutoLoad) {
                showToast('Configuration loaded successfully! You can now update the fields.', 'success');
            }
        } catch (error) {
            showToast('Error: ' + error.message, 'error');
        } finally {
            loadConfigBtn.disabled = false;
            loadConfigBtn.textContent = 'Load Configuration';
        }
    });

    const configForm = document.getElementById('config-form');
    if (configForm) {
        configForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const spinner = document.querySelector('.spinner-border');
            spinner.style.display = 'inline-block';
            
            const isUpdateMode = modeUpdate.checked;
            const manifestUrl = isUpdateMode 
                ? await updateConfiguration() 
                : await getManifestUrl(true);
            
            if (manifestUrl) {
                if (!isUpdateMode) {
                    window.location.href = manifestUrl;
                } else {
                    displayFallbackUrl(manifestUrl);
                    showToast('Configuration updated successfully!', 'success');
                }
            }
            spinner.style.display = 'none';
        });
    }

    document.getElementById('shareBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        const manifestUrl = await getManifestUrl();
        if (manifestUrl) {
            try {
                await navigator.share({
                    title: 'EyePeaTeaVea Addon Manifest',
                    url: manifestUrl,
                });
            } catch (error) {
                displayFallbackUrl(manifestUrl);
                showToast('Unable to use Share API. URL is ready to be copied manually.', 'info');
            }
        }
    });

    document.getElementById('copyBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        const manifestUrl = await getManifestUrl();
        if (manifestUrl) {
            copyToClipboard(manifestUrl);
        }
    });

    document.getElementById('copyBtnResult').addEventListener('click', () => {
        const manifestUrl = document.getElementById('manifest_url').value;
        copyToClipboard(manifestUrl);
    });
});

async function getManifestUrl(isRedirect = false) {
    const m3uSources = document.getElementById('m3u_sources').value.split('\n').filter(url => url.trim() !== '');
    const parserScheduleCrontab = document.getElementById('parser_schedule_crontab').value;
    const hostUrl = document.getElementById('host_url').value;
    const addonPassword = document.getElementById('addon_password').value;
    const timezone = document.getElementById('timezone').value || null;

    const data = {
        m3u_sources: m3uSources,
        parser_schedule_crontab: parserScheduleCrontab,
        host_url: hostUrl,
        addon_password: addonPassword || null,
        timezone: timezone
    };

    try {
        const response = await fetch('/configure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'An unknown error occurred.');
        }

        const result = await response.json();
        const secret_str = result.secret_str;
        
        let urlPrefix = window.location.protocol + "//";
        if (isRedirect) {
            urlPrefix = "stremio://";
        }

        // Normalize hostUrl: remove protocol and trailing slashes
        const normalizedHost = hostUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
        const manifestUrl = `${urlPrefix}${normalizedHost}/${secret_str}/manifest.json`;
        
        const resultDiv = document.getElementById('result');
        const manifestUrlInput = document.getElementById('manifest_url');
        manifestUrlInput.value = manifestUrl;
        resultDiv.style.display = 'block';

        generateQRCode(manifestUrl);
        
        // Generate and display dashboard QR code and link
        displayDashboardInfo(secret_str, hostUrl);

        return manifestUrl;

    } catch (error) {
        showToast('Error: ' + error.message, 'error');
        return null;
    }
}

function displayFallbackUrl(url) {
    const resultDiv = document.getElementById('result');
    const manifestUrlInput = document.getElementById('manifest_url');
    manifestUrlInput.value = url;
    resultDiv.style.display = 'block';
    manifestUrlInput.focus();
    manifestUrlInput.select();
    generateQRCode(url);
}

function generateQRCode(url) {
    const qr = qrcode(0, 'L');
    qr.addData(url);
    qr.make();
    document.getElementById('qrcode').innerHTML = qr.createImgTag(4);
}

function displayDashboardInfo(secretStr, hostUrl) {
    // Normalize hostUrl: remove protocol and trailing slashes
    const normalizedHost = hostUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
    // Use the same protocol as the current page
    const protocol = window.location.protocol;
    const dashboardUrl = `${protocol}//${normalizedHost}/user/${secretStr}/dashboard`;
    
    // Check if dashboard section already exists
    let dashboardSection = document.getElementById('dashboard-section');
    if (!dashboardSection) {
        // Create dashboard section after the manifest URL section
        const resultDiv = document.getElementById('result');
        dashboardSection = document.createElement('div');
        dashboardSection.id = 'dashboard-section';
        dashboardSection.className = 'mt-4';
        resultDiv.appendChild(dashboardSection);
    }
    
    dashboardSection.innerHTML = `
        <h2>Your Personal Dashboard:</h2>
        <p class="text-muted">Access your personal dashboard to view channels, manage logo overrides, and monitor your configuration.</p>
        <div class="input-group mb-3">
            <input type="text" class="form-control" id="dashboard_url" value="${dashboardUrl}" readonly>
            <button class="btn btn-outline-secondary" type="button" id="copyDashboardBtn">Copy</button>
        </div>
        <div id="dashboard-qrcode" class="text-center mb-3"></div>
        <p class="text-muted small">
            <i class="bi bi-info-circle"></i> 
            Bookmark this dashboard URL or scan the QR code to easily access your configuration dashboard anytime.
        </p>
    `;
    
    // Generate QR code for dashboard
    const dashboardQr = qrcode(0, 'L');
    dashboardQr.addData(dashboardUrl);
    dashboardQr.make();
    document.getElementById('dashboard-qrcode').innerHTML = dashboardQr.createImgTag(4);
    
    // Add copy button handler
    document.getElementById('copyDashboardBtn').addEventListener('click', () => {
        const dashboardUrlInput = document.getElementById('dashboard_url');
        dashboardUrlInput.focus();
        dashboardUrlInput.select();
        copyToClipboard(dashboardUrl, 'Dashboard URL copied to clipboard!');
    });
}

async function updateConfiguration() {
    const secretStr = document.getElementById('secret_str').value.trim();
    if (!secretStr) {
        showToast('Please enter your secret_str', 'warning');
        return null;
    }

    const m3uSources = document.getElementById('m3u_sources').value.split('\n').filter(url => url.trim() !== '');
    const parserScheduleCrontab = document.getElementById('parser_schedule_crontab').value.trim();
    const hostUrl = document.getElementById('host_url').value.trim();
    const addonPassword = document.getElementById('addon_password').value;
    const timezone = document.getElementById('timezone').value || null;

    // Build update payload - only include fields that have values
    // Empty string for password means remove password
    const data = {};
    if (m3uSources.length > 0) data.m3u_sources = m3uSources;
    if (parserScheduleCrontab) data.parser_schedule_crontab = parserScheduleCrontab;
    if (hostUrl) data.host_url = hostUrl;
    // Always include password field - empty string means remove, undefined means don't change
    // But since we're updating, we should send the current value (even if empty)
    data.addon_password = addonPassword || '';
    // Include timezone if set
    if (timezone) data.timezone = timezone;

    try {
        const response = await fetch(`/${secretStr}/configure`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'An unknown error occurred.');
        }

        const result = await response.json();
        // Normalize hostUrl: remove protocol and trailing slashes
        const normalizedHost = hostUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
        const manifestUrl = `${normalizedHost}/${secretStr}/manifest.json`;
        
        return manifestUrl;

    } catch (error) {
        showToast('Error: ' + error.message, 'error');
        return null;
    }
}

function clearForm() {
    document.getElementById('m3u_sources').value = '';
    document.getElementById('parser_schedule_crontab').value = '0 */6 * * *';
    document.getElementById('host_url').value = window.location.origin;
    document.getElementById('addon_password').value = '';
    document.getElementById('secret_str').value = '';
    document.getElementById('result').style.display = 'none';
    // Reset timezone to auto-detect
    const timezoneSelect = document.getElementById('timezone');
    if (timezoneSelect) {
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        timezoneSelect.value = browserTimezone || '';
    }
}

function copyToClipboard(text, successMessage = 'Manifest URL copied to clipboard!') {
    try {
        navigator.clipboard.writeText(text);
        showToast(successMessage, 'success');
    } catch (error) {
        showToast('Unable to access clipboard. URL is ready to be copied manually.', 'warning');
    }
}