// Extract secret_str from URL path: /user/{secret_str}/dashboard
function getSecretStrFromUrl() {
    const match = window.location.pathname.match(/^\/user\/([^\/]+)\/dashboard/);
    if (match) {
        return match[1];
    }
    return null;
}

const secretStr = getSecretStrFromUrl();
const API_BASE = `/user/${secretStr}/api`;

async function loadDashboard() {
    if (!secretStr) {
        showError('Invalid URL. Please use the dashboard link provided when you created your configuration.');
        return;
    }

    try {
        // Load user info
        const infoResponse = await fetch(`${API_BASE}/info`);
        if (!infoResponse.ok) {
            if (infoResponse.status === 404) {
                throw new Error('User configuration not found. Please check your dashboard URL.');
            }
            throw new Error('Failed to load dashboard information.');
        }

        const info = await infoResponse.json();
        
        // Update stats
        document.getElementById('channel-count').textContent = info.channel_count || 0;
        document.getElementById('event-count').textContent = info.event_count || 0;
        document.getElementById('m3u-count').textContent = info.m3u_source_count || 0;
        document.getElementById('host-url').textContent = info.host_url || '-';
        document.getElementById('timezone').textContent = info.timezone || 'Auto-detect';
        document.getElementById('has-password').textContent = info.has_password ? 'Yes' : 'No';
        
        // Update links (with null checks)
        const manifestUrl = `${info.host_url}/${secretStr}/manifest.json`;
        const manifestLink = document.getElementById('manifest-link');
        const updateConfigLink = document.getElementById('update-config-link');
        const configureLink = document.getElementById('configure-link');
        const configureLink2 = document.getElementById('configure-link-2');
        
        if (manifestLink) manifestLink.href = manifestUrl;
        if (updateConfigLink) updateConfigLink.href = `/${secretStr}/configure`;
        if (configureLink) configureLink.href = `/${secretStr}/configure`;
        if (configureLink2) configureLink2.href = `/${secretStr}/configure`;

        // Load logo overrides
        await loadLogoOverrides();
        
        // Load channels and events
        await loadChannels();
        await loadEvents();

        // Show dashboard content
        document.getElementById('loading').style.display = 'none';
        document.getElementById('dashboard-content').style.display = 'block';

    } catch (error) {
        console.error('Error loading dashboard:', error);
        showError(error.message);
    }
}

async function loadLogoOverrides() {
    try {
        const response = await fetch(`${API_BASE}/logo-overrides`);
        if (!response.ok) {
            throw new Error('Failed to load logo overrides.');
        }

        const data = await response.json();
        const overrides = data.overrides || [];
        
        document.getElementById('override-count').textContent = overrides.length;

        const listElement = document.getElementById('logo-overrides-list');
        if (overrides.length === 0) {
            listElement.innerHTML = '<p class="text-muted">No logo overrides configured.</p>';
        } else {
            let html = '<div class="table-responsive"><table class="table table-sm">';
            html += '<thead><tr><th>Channel ID</th><th>Logo URL</th><th>Type</th><th>Actions</th></tr></thead><tbody>';
            
            overrides.forEach(override => {
                const tvgId = override.tvg_id || '';
                const logoUrl = override.logo_url || '';
                const isRegex = override.is_regex ? 'Regex' : 'Exact';
                const badgeClass = override.is_regex ? 'bg-info' : 'bg-success';
                const escapedTvgId = escapeHtml(tvgId).replace(/'/g, "\\'");
                
                html += `<tr>
                    <td><code>${escapeHtml(tvgId)}</code></td>
                    <td><a href="${escapeHtml(logoUrl)}" target="_blank" class="text-truncate d-inline-block" style="max-width: 300px;">${escapeHtml(logoUrl)}</a></td>
                    <td><span class="badge ${badgeClass}">${isRegex}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteLogoOverride('${escapedTvgId}')">
                            <i class="bi bi-trash"></i> Delete
                        </button>
                    </td>
                </tr>`;
            });
            
            html += '</tbody></table></div>';
            listElement.innerHTML = html;
        }
    } catch (error) {
        console.error('Error loading logo overrides:', error);
        document.getElementById('logo-overrides-list').innerHTML = 
            '<p class="text-danger">Failed to load logo overrides.</p>';
    }
}

function showError(message) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error').style.display = 'block';
    document.getElementById('error-message').textContent = message;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Logo override functions
function exportLogoOverrides() {
    (async () => {
        try {
            const response = await fetch(`${API_BASE}/logo-overrides/export`);
            if (!response.ok) {
                throw new Error('Failed to export logo overrides.');
            }

            const data = await response.json();
            const jsonStr = JSON.stringify(data, null, 2);
            
            // Create download link
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logo-overrides-${secretStr.substring(0, 8)}-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            showNotification('Logo overrides exported successfully!', 'success');
        } catch (error) {
            console.error('Error exporting logo overrides:', error);
            showNotification('Failed to export logo overrides: ' + error.message, 'error');
        }
    })();
}

function showImportModal() {
    // Clear previous import data
    document.getElementById('import-file').value = '';
    document.getElementById('import-text').value = '';
    document.getElementById('import-result').style.display = 'none';
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('importModal'));
    modal.show();
}

function submitImport() {
    (async () => {
        const fileInput = document.getElementById('import-file');
        const textInput = document.getElementById('import-text');
        const resultDiv = document.getElementById('import-result');
        
        let importData = null;
        
        // Check if file was uploaded
        if (fileInput.files && fileInput.files.length > 0) {
            const file = fileInput.files[0];
            try {
                const text = await file.text();
                importData = JSON.parse(text);
            } catch (error) {
                resultDiv.className = 'alert alert-danger';
                resultDiv.textContent = `Error reading file: ${error.message}`;
                resultDiv.style.display = 'block';
                return;
            }
        } else if (textInput.value.trim()) {
            // Use text input
            try {
                importData = JSON.parse(textInput.value.trim());
            } catch (error) {
                resultDiv.className = 'alert alert-danger';
                resultDiv.textContent = `Invalid JSON: ${error.message}`;
                resultDiv.style.display = 'block';
                return;
            }
        } else {
            resultDiv.className = 'alert alert-warning';
            resultDiv.textContent = 'Please upload a file or paste JSON data.';
            resultDiv.style.display = 'block';
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/logo-overrides/import`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(importData)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Import failed');
            }
            
            const result = await response.json();
            
            // Show results
            let message = `Import completed! `;
            message += `Imported: ${result.imported}, Updated: ${result.updated}`;
            if (result.errors > 0) {
                message += `, Errors: ${result.errors}`;
            }
            
            if (result.error_details && result.error_details.length > 0) {
                message += '\n\nErrors:\n' + result.error_details.join('\n');
            }
            
            resultDiv.className = 'alert alert-success';
            resultDiv.innerHTML = message.replace(/\n/g, '<br>');
            resultDiv.style.display = 'block';
            
            // Reload logo overrides and dashboard info
            setTimeout(() => {
                loadLogoOverrides();
                loadDashboard();
                const modal = bootstrap.Modal.getInstance(document.getElementById('importModal'));
                if (modal) {
                    modal.hide();
                }
            }, 2000);
            
        } catch (error) {
            resultDiv.className = 'alert alert-danger';
            resultDiv.textContent = `Import failed: ${error.message}`;
            resultDiv.style.display = 'block';
        }
    })();
}

function showNotification(message, type = 'info') {
    // Create a simple notification (could be enhanced with Bootstrap toast)
    const alertClass = type === 'success' ? 'alert-success' : type === 'error' ? 'alert-danger' : 'alert-info';
    const notification = document.createElement('div');
    notification.className = `alert ${alertClass} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
    notification.style.zIndex = '9999';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Pagination state
let currentChannelsPage = 1;
let currentEventsPage = 1;

// Load channels
async function loadChannels(page = null) {
    if (page !== null) {
        currentChannelsPage = page;
    }
    const container = document.getElementById('channels-list');
    container.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"></div></div>';
    
    try {
        const search = document.getElementById('channel-search').value;
        const response = await fetch(`${API_BASE}/channels?page=${currentChannelsPage}&per_page=50${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (!response.ok) {
            throw new Error('Failed to load channels');
        }
        
        const data = await response.json();
        displayChannels(data.channels || [], data.pagination || {});
    } catch (error) {
        console.error('Error loading channels:', error);
        document.getElementById('channels-list').innerHTML = 
            '<div class="alert alert-danger">Failed to load channels</div>';
    }
}

function displayChannels(channels, pagination) {
    const container = document.getElementById('channels-list');
    
    if (channels.length === 0) {
        container.innerHTML = '<p class="text-muted">No channels found</p>';
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-sm table-hover">';
    html += '<thead><tr><th>Channel Name</th><th>Group</th><th>Channel ID</th><th>Logo</th></tr></thead><tbody>';
    
    channels.forEach(channel => {
        const tvgName = escapeHtml(channel.tvg_name || channel.tvg_id || 'N/A');
        const groupTitle = escapeHtml(channel.group_title || 'N/A');
        const tvgId = escapeHtml(channel.tvg_id || '');
        const logoUrl = channel.tvg_logo || '';
        
        html += `<tr>
            <td><strong>${tvgName}</strong></td>
            <td><span class="badge bg-secondary">${groupTitle}</span></td>
            <td><code>${tvgId}</code></td>
            <td>${logoUrl ? `<img src="${escapeHtml(logoUrl)}" alt="Logo" style="max-height: 30px;" onerror="this.style.display='none'">` : 'N/A'}</td>
        </tr>`;
    });
    
    html += '</tbody></table></div>';
    
    // Add pagination
    if (pagination.pages > 1) {
        html += '<nav><ul class="pagination justify-content-center mt-3">';
        html += `<li class="page-item ${pagination.page === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadChannelsPage(${pagination.page - 1}); return false;">Previous</a>
        </li>`;
        html += `<li class="page-item active"><span class="page-link">Page ${pagination.page} of ${pagination.pages}</span></li>`;
        html += `<li class="page-item ${pagination.page >= pagination.pages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadChannelsPage(${pagination.page + 1}); return false;">Next</a>
        </li>`;
        html += '</ul></nav>';
    }
    
    container.innerHTML = html;
}

function loadChannelsPage(page) {
    loadChannels(page);
}

function searchChannels() {
    currentChannelsPage = 1;
    loadChannels(1);
}

// Load events
async function loadEvents(page = null) {
    if (page !== null) {
        currentEventsPage = page;
    }
    const container = document.getElementById('events-list');
    container.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"></div></div>';
    
    try {
        const search = document.getElementById('event-search').value;
        const response = await fetch(`${API_BASE}/events?page=${currentEventsPage}&per_page=50${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (!response.ok) {
            throw new Error('Failed to load events');
        }
        
        const data = await response.json();
        displayEvents(data.events || [], data.pagination || {});
    } catch (error) {
        console.error('Error loading events:', error);
        document.getElementById('events-list').innerHTML = 
            '<div class="alert alert-danger">Failed to load events</div>';
    }
}

function displayEvents(events, pagination) {
    const container = document.getElementById('events-list');
    
    if (events.length === 0) {
        container.innerHTML = '<p class="text-muted">No events found</p>';
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-sm table-hover">';
    html += '<thead><tr><th>Event Title</th><th>Sport</th><th>Date/Time</th><th>Channel ID</th></tr></thead><tbody>';
    
    events.forEach(event => {
        const eventTitle = escapeHtml(event.event_title || 'N/A');
        const eventSport = escapeHtml(event.event_sport || 'N/A');
        const eventDateTime = escapeHtml(event.event_datetime_full || 'N/A');
        const tvgId = escapeHtml(event.tvg_id || '');
        
        html += `<tr>
            <td><strong>${eventTitle}</strong></td>
            <td><span class="badge bg-info">${eventSport}</span></td>
            <td>${eventDateTime}</td>
            <td><code>${tvgId}</code></td>
        </tr>`;
    });
    
    html += '</tbody></table></div>';
    
    // Add pagination
    if (pagination.pages > 1) {
        html += '<nav><ul class="pagination justify-content-center mt-3">';
        html += `<li class="page-item ${pagination.page === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadEventsPage(${pagination.page - 1}); return false;">Previous</a>
        </li>`;
        html += `<li class="page-item active"><span class="page-link">Page ${pagination.page} of ${pagination.pages}</span></li>`;
        html += `<li class="page-item ${pagination.page >= pagination.pages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadEventsPage(${pagination.page + 1}); return false;">Next</a>
        </li>`;
        html += '</ul></nav>';
    }
    
    container.innerHTML = html;
}

function loadEventsPage(page) {
    loadEvents(page);
}

function searchEvents() {
    currentEventsPage = 1;
    loadEvents(1);
}

// Logo override functions
function showAddLogoOverrideModal() {
    const modal = new bootstrap.Modal(document.getElementById('logoOverrideModal'));
    document.getElementById('logoOverrideForm').reset();
    document.getElementById('overrideIsRegex').checked = false;
    document.getElementById('logoOverrideError').style.display = 'none';
    document.getElementById('logoOverrideSuccess').style.display = 'none';
    
    // Load channels into dropdown
    loadChannelsForOverride();
    
    modal.show();
}

async function loadChannelsForOverride() {
    try {
        const response = await fetch(`${API_BASE}/channels?per_page=1000`);
        if (!response.ok) {
            return;
        }
        
        const data = await response.json();
        const select = document.getElementById('channel-select');
        select.innerHTML = '<option value="">-- Select a channel --</option>';
        
        (data.channels || []).forEach(channel => {
            const option = document.createElement('option');
            option.value = channel.tvg_id || '';
            option.textContent = `${channel.tvg_name || channel.tvg_id} (${channel.tvg_id})`;
            option.dataset.logoUrl = channel.tvg_logo || '';
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading channels for override:', error);
    }
}

function selectChannelForOverride() {
    const select = document.getElementById('channel-select');
    const selectedOption = select.options[select.selectedIndex];
    if (selectedOption && selectedOption.value) {
        document.getElementById('overrideTvgId').value = selectedOption.value;
        const logoUrl = selectedOption.dataset.logoUrl;
        if (logoUrl) {
            document.getElementById('overrideLogoUrl').value = logoUrl;
        }
    }
}

function submitLogoOverride() {
    const tvgId = document.getElementById('overrideTvgId').value.trim();
    const logoUrl = document.getElementById('overrideLogoUrl').value.trim();
    const isRegex = document.getElementById('overrideIsRegex').checked;
    const errorDiv = document.getElementById('logoOverrideError');
    const successDiv = document.getElementById('logoOverrideSuccess');
    
    errorDiv.style.display = 'none';
    successDiv.style.display = 'none';
    
    if (!tvgId || !logoUrl) {
        errorDiv.textContent = 'Please fill in all fields';
        errorDiv.style.display = 'block';
        return;
    }
    
    // Validate regex if is_regex is checked
    if (isRegex) {
        try {
            new RegExp(tvgId);
        } catch (e) {
            errorDiv.textContent = `Invalid regex pattern: ${e.message}`;
            errorDiv.style.display = 'block';
            return;
        }
    }
    
    createLogoOverride(tvgId, logoUrl, isRegex);
}

async function createLogoOverride(tvgId, logoUrl, isRegex = false) {
    const errorDiv = document.getElementById('logoOverrideError');
    const successDiv = document.getElementById('logoOverrideSuccess');
    
    errorDiv.style.display = 'none';
    successDiv.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/logo-overrides`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tvg_id: tvgId,
                logo_url: logoUrl,
                is_regex: isRegex
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to create logo override');
        }
        
        successDiv.textContent = 'Logo override created successfully!';
        successDiv.style.display = 'block';
        
        // Reload logo overrides and close modal after delay
        setTimeout(() => {
            loadLogoOverrides();
            loadDashboard();
            const modal = bootstrap.Modal.getInstance(document.getElementById('logoOverrideModal'));
            if (modal) {
                modal.hide();
            }
        }, 1500);
        
    } catch (error) {
        errorDiv.textContent = `Error: ${error.message}`;
        errorDiv.style.display = 'block';
    }
}

async function deleteLogoOverride(tvgId) {
    if (!confirm(`Are you sure you want to delete the logo override for "${tvgId}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/logo-overrides/${encodeURIComponent(tvgId)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to delete logo override');
        }
        
        showNotification('Logo override deleted successfully!', 'success');
        
        // Reload logo overrides
        loadLogoOverrides();
        loadDashboard();
        
    } catch (error) {
        showNotification(`Failed to delete logo override: ${error.message}`, 'error');
    }
}

// Load dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    
    // Add Enter key handlers for search (after page loads)
    setTimeout(() => {
        const channelSearch = document.getElementById('channel-search');
        const eventSearch = document.getElementById('event-search');
        
        if (channelSearch) {
            channelSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    searchChannels();
                }
            });
        }
        
        if (eventSearch) {
            eventSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    searchEvents();
                }
            });
        }
    }, 1000);
});
