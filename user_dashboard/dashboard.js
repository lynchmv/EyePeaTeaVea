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
        
        // Update links
        const manifestUrl = `${info.host_url}/${secretStr}/manifest.json`;
        document.getElementById('manifest-link').href = manifestUrl;
        document.getElementById('configure-link').href = `/${secretStr}/configure`;
        document.getElementById('configure-link-2').href = `/${secretStr}/configure`;

        // Load logo overrides
        await loadLogoOverrides();

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
            html += '<thead><tr><th>Channel ID</th><th>Logo URL</th><th>Type</th></tr></thead><tbody>';
            
            overrides.forEach(override => {
                const tvgId = override.tvg_id || '';
                const logoUrl = override.logo_url || '';
                const isRegex = override.is_regex ? 'Regex' : 'Exact';
                const badgeClass = override.is_regex ? 'bg-info' : 'bg-success';
                
                html += `<tr>
                    <td><code>${escapeHtml(tvgId)}</code></td>
                    <td><a href="${escapeHtml(logoUrl)}" target="_blank" class="text-truncate d-inline-block" style="max-width: 300px;">${escapeHtml(logoUrl)}</a></td>
                    <td><span class="badge ${badgeClass}">${isRegex}</span></td>
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

// Load dashboard when page loads
document.addEventListener('DOMContentLoaded', loadDashboard);
