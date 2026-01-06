// Admin Dashboard JavaScript

const API_BASE = '/admin';
const ASSETS_BASE = '/admin-assets';

// Helper function for API fetch requests
async function apiFetch(url, options = {}) {
    const defaultOptions = {
        credentials: 'include',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            ...options.headers
        }
    };
    return fetch(url, { ...defaultOptions, ...options });
}

// State management
let currentUser = null;
let currentPage = 'dashboard';

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    setupEventListeners();
});

// Check authentication status
async function checkAuth() {
    try {
        const response = await apiFetch(`${API_BASE}/me`);
        
        if (response.ok) {
            currentUser = await response.json();
            showDashboard();
        } else {
            showLogin();
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showLogin();
    }
}

// Setup event listeners
function setupEventListeners() {
    // Login form
    document.getElementById('loginForm').addEventListener('submit', handleLogin);
    
    // Logout button
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
    
    // Sidebar navigation
    document.querySelectorAll('.sidebar-menu a[data-page]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = e.target.closest('a').dataset.page;
            navigateToPage(page);
        });
    });
    
    // User search
    document.getElementById('searchBtn').addEventListener('click', () => {
        loadUsers();
    });
    document.getElementById('userSearch').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadUsers();
        }
    });
    
    // Channel search
    document.getElementById('channelSearchBtn').addEventListener('click', () => {
        loadChannels();
    });
    document.getElementById('channelSearch').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadChannels();
        }
    });
    
    // Event search
    document.getElementById('eventSearchBtn').addEventListener('click', () => {
        loadEvents();
    });
    document.getElementById('eventSearch').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadEvents();
        }
    });
    
    // Password change form
    document.getElementById('changePasswordForm').addEventListener('submit', handlePasswordChange);
    
    // Clickable stat cards
    document.querySelectorAll('.clickable-card').forEach(card => {
        card.addEventListener('click', (e) => {
            const page = e.currentTarget.dataset.page;
            if (page) {
                navigateToPage(page);
            }
        });
    });
}

// Handle login
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorDiv = document.getElementById('loginError');
    
    errorDiv.classList.add('hidden');
    
    try {
        const response = await apiFetch(`${API_BASE}/login`, {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        
        if (response.ok) {
            const data = await response.json();
            currentUser = data;
            showDashboard();
        } else {
            const error = await response.json();
            errorDiv.textContent = error.detail || 'Login failed';
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

// Handle logout
async function handleLogout() {
    try {
        await apiFetch(`${API_BASE}/logout`, {
            method: 'POST'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    showLogin();
}

// Show login screen
function showLogin() {
    document.getElementById('loginScreen').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');
    currentUser = null;
}

// Show dashboard
function showDashboard() {
    document.getElementById('loginScreen').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    
    if (currentUser) {
        document.getElementById('currentUser').textContent = currentUser.username;
        document.getElementById('userRole').textContent = currentUser.role;
    }
    
    // Navigate to page from URL or default to dashboard
    const page = getPageFromPath();
    navigateToPage(page, false); // Don't update history on initial load
}

// Navigate to page
function navigateToPage(page, updateHistory = true) {
    currentPage = page;
    
    // Update URL without hash using History API
    if (updateHistory) {
        const newUrl = `/admin/${page === 'dashboard' ? '' : page}`;
        window.history.pushState({ page }, '', newUrl);
    }
    
    // Update sidebar active state
    document.querySelectorAll('.sidebar-menu a').forEach(link => {
        link.classList.remove('active');
        if (link.dataset.page === page) {
            link.classList.add('active');
        }
    });
    
    // Hide all pages
    document.querySelectorAll('.page-content').forEach(p => {
        p.classList.add('hidden');
    });
    
    // Show selected page
    const pageElement = document.getElementById(`${page}Page`);
    if (pageElement) {
        pageElement.classList.remove('hidden');
        document.getElementById('pageTitle').textContent = getPageTitle(page);
        
        // Load page data
        switch(page) {
            case 'dashboard':
                loadDashboard();
                break;
            case 'users':
                loadUsers();
                break;
            case 'system':
                loadSystem();
                break;
            case 'logs':
                loadLogs();
                break;
            case 'settings':
                loadSettings();
                break;
            case 'channels':
                loadChannels();
                break;
            case 'events':
                loadEvents();
                break;
        }
    }
}

// Handle browser back/forward buttons
window.addEventListener('popstate', (event) => {
    const page = event.state?.page || getPageFromPath();
    navigateToPage(page, false);
});

// Get page from current path
function getPageFromPath() {
    const path = window.location.pathname;
    if (path === '/admin' || path === '/admin/') {
        return 'dashboard';
    }
    const match = path.match(/^\/admin\/([^/]+)/);
    if (match) {
        const page = match[1];
        // Validate page exists
        const validPages = ['dashboard', 'users', 'channels', 'events', 'system', 'logs', 'settings'];
        if (validPages.includes(page)) {
            return page;
        }
    }
    return 'dashboard';
}

// Get page title
function getPageTitle(page) {
    const titles = {
        'dashboard': 'Dashboard',
        'users': 'User Management',
        'system': 'System Information',
        'logs': 'Audit Logs',
        'settings': 'Settings',
        'channels': 'All Channels',
        'events': 'All Events'
    };
    return titles[page] || 'Dashboard';
}

// Load dashboard data
async function loadDashboard() {
    try {
        // Load stats
        const statsResponse = await apiFetch(`${API_BASE}/stats`);
        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            document.getElementById('statUsers').textContent = stats.total_users || 0;
            document.getElementById('statChannels').textContent = stats.total_channels || 0;
            document.getElementById('statEvents').textContent = stats.total_events || 0;
            document.getElementById('statJobs').textContent = stats.active_scheduler_jobs || 0;
        }
        
        // Load health
        const healthResponse = await apiFetch(`${API_BASE}/health`);
        if (healthResponse.ok) {
            const health = await healthResponse.json();
            displayHealth(health);
        }
        
        // Load recent logs
        const logsResponse = await apiFetch(`${API_BASE}/logs?limit=10`);
        if (logsResponse.ok) {
            const logsData = await logsResponse.json();
            displayRecentActivity(logsData.logs || []);
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

// Display health status
function displayHealth(health) {
    const container = document.getElementById('healthStatus');
    container.innerHTML = '';
    
    const checks = health.checks || {};
    const statusColors = {
        'healthy': 'success',
        'degraded': 'warning',
        'unhealthy': 'danger'
    };
    
    for (const [check, data] of Object.entries(checks)) {
        const status = data.status || 'unknown';
        const color = statusColors[status] || 'secondary';
        
        const div = document.createElement('div');
        div.className = `d-flex justify-content-between align-items-center mb-2 p-2 bg-light rounded`;
        div.innerHTML = `
            <span><strong>${check.charAt(0).toUpperCase() + check.slice(1)}</strong></span>
            <span class="badge bg-${color}">${status}</span>
        `;
        container.appendChild(div);
    }
}

// Display recent activity
function displayRecentActivity(logs) {
    const container = document.getElementById('recentActivity');
    container.innerHTML = '';
    
    if (logs.length === 0) {
        container.innerHTML = '<p class="text-muted">No recent activity</p>';
        return;
    }
    
    logs.slice(0, 10).forEach(log => {
        const div = document.createElement('div');
        div.className = 'mb-2 p-2 bg-light rounded';
        const time = new Date(log.timestamp).toLocaleString();
        div.innerHTML = `
            <div class="d-flex justify-content-between">
                <span><strong>${log.username}</strong> - ${log.action}</span>
                <small class="text-muted">${time}</small>
            </div>
            ${log.resource ? `<small class="text-muted">${log.resource}</small>` : ''}
        `;
        container.appendChild(div);
    });
}

// Load users
async function loadUsers() {
    const container = document.getElementById('usersTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const search = document.getElementById('userSearch').value;
        const response = await apiFetch(`${API_BASE}/users?per_page=50${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (response.ok) {
            const data = await response.json();
            displayUsers(data.users || [], data.pagination || {});
        } else {
            container.innerHTML = '<div class="alert alert-danger">Failed to load users</div>';
        }
    } catch (error) {
        console.error('Error loading users:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading users</div>';
    }
}

// Display users table
function displayUsers(users, pagination) {
    const container = document.getElementById('usersTable');
    
    if (users.length === 0) {
        container.innerHTML = '<p class="text-muted">No users found</p>';
        return;
    }
    
    let html = `
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>Secret String</th>
                    <th>Channels</th>
                    <th>Events</th>
                    <th>M3U Sources</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    users.forEach(user => {
        const statusClass = {
            'active': 'badge-active',
            'warning': 'badge-warning',
            'error': 'badge-error'
        }[user.status] || 'badge-secondary';
        
        html += `
            <tr>
                <td><code>${user.secret_str.substring(0, 16)}...</code></td>
                <td>${user.channel_count}</td>
                <td>${user.event_count}</td>
                <td>${user.m3u_source_count}</td>
                <td><span class="badge-status ${statusClass}">${user.status}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="viewUser('${user.secret_str}')">
                        <i class="bi bi-eye"></i>
                    </button>
                    ${currentUser && currentUser.role !== 'viewer' ? `
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteUser('${user.secret_str}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    if (pagination.pages > 1) {
        html += `
            <nav>
                <ul class="pagination justify-content-center">
                    <li class="page-item ${pagination.page === 1 ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadUsersPage(${pagination.page - 1}); return false;">Previous</a>
                    </li>
                    <li class="page-item active">
                        <span class="page-link">Page ${pagination.page} of ${pagination.pages}</span>
                    </li>
                    <li class="page-item ${pagination.page >= pagination.pages ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadUsersPage(${pagination.page + 1}); return false;">Next</a>
                    </li>
                </ul>
            </nav>
        `;
    }
    
    container.innerHTML = html;
}

// Load users page
function loadUsersPage(page) {
    // Implementation would update pagination
    loadUsers();
}

// View user details
async function viewUser(secretStr) {
    const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
    const content = document.getElementById('userDetailContent');
    const triggerParseBtn = document.getElementById('triggerParseBtn');
    const deleteUserBtn = document.getElementById('deleteUserBtn');
    
    // Show modal with loading state
    content.innerHTML = '<div class="loading"><div class="spinner-border text-primary" role="status"></div></div>';
    modal.show();
    
    // Hide action buttons initially
    triggerParseBtn.style.display = 'none';
    deleteUserBtn.style.display = 'none';
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}`);
        
        if (response.ok) {
            const user = await response.json();
            
            // Build user details HTML
            let html = `
                <div class="mb-3">
                    <h6>Configuration</h6>
                    <table class="table table-sm">
                        <tr>
                            <th width="40%">Secret String:</th>
                            <td><code>${user.secret_str}</code></td>
                        </tr>
                        <tr>
                            <th>Schedule:</th>
                            <td><code>${user.configuration.parser_schedule_crontab}</code></td>
                        </tr>
                        <tr>
                            <th>Host URL:</th>
                            <td><a href="${user.configuration.host_url}" target="_blank">${user.configuration.host_url}</a></td>
                        </tr>
                        <tr>
                            <th>Password Protected:</th>
                            <td>${user.configuration.has_password ? '<span class="badge bg-success">Yes</span>' : '<span class="badge bg-secondary">No</span>'}</td>
                        </tr>
                        <tr>
                            <th>Timezone:</th>
                            <td>${user.configuration.timezone || 'Not set'}</td>
                        </tr>
                    </table>
                </div>
                
                <div class="mb-3">
                    <h6>M3U Sources</h6>
                    <ul class="list-group">
            `;
            
            user.configuration.m3u_sources.forEach((source, index) => {
                html += `<li class="list-group-item"><small><code>${source}</code></small></li>`;
            });
            
            html += `
                    </ul>
                </div>
                
                <div class="mb-3">
                    <h6>Statistics</h6>
                    <div class="row">
                        <div class="col-md-4">
                            <div class="card text-center">
                                <div class="card-body">
                                    <h3 class="card-title">${user.statistics.channel_count}</h3>
                                    <p class="card-text text-muted">Channels</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card text-center">
                                <div class="card-body">
                                    <h3 class="card-title">${user.statistics.event_count}</h3>
                                    <p class="card-text text-muted">Events</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card text-center">
                                <div class="card-body">
                                    <h3 class="card-title">${user.statistics.epg_channel_count}</h3>
                                    <p class="card-text text-muted">EPG Channels</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="mb-3">
                    <h6>Stremio Manifest URL</h6>
                    <div class="input-group">
                        <input type="text" class="form-control" id="manifestUrl" value="${user.configuration.host_url}/${user.secret_str}/manifest.json" readonly>
                        <button class="btn btn-outline-secondary" type="button" onclick="copyToClipboard('manifestUrl')">
                            <i class="bi bi-clipboard"></i> Copy
                        </button>
                    </div>
                </div>
            `;
            
            content.innerHTML = html;
            
            // Show action buttons if user has admin role
            if (currentUser && currentUser.role !== 'viewer') {
                triggerParseBtn.style.display = 'inline-block';
                triggerParseBtn.onclick = () => triggerUserParse(secretStr);
                deleteUserBtn.style.display = 'inline-block';
                deleteUserBtn.onclick = () => {
                    modal.hide();
                    deleteUser(secretStr);
                };
            }
        } else {
            content.innerHTML = '<div class="alert alert-danger">Failed to load user details</div>';
        }
    } catch (error) {
        console.error('Error viewing user:', error);
        content.innerHTML = '<div class="alert alert-danger">Error loading user details</div>';
    }
}

// Copy to clipboard helper
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    element.select();
    element.setSelectionRange(0, 99999); // For mobile devices
    navigator.clipboard.writeText(element.value).then(() => {
        // Show temporary success feedback
        const btn = event.target.closest('button');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check"></i> Copied!';
        btn.classList.add('btn-success');
        btn.classList.remove('btn-outline-secondary');
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-secondary');
        }, 2000);
    });
}

// Trigger user parse
async function triggerUserParse(secretStr) {
    if (!confirm(`Trigger manual parse for user ${secretStr.substring(0, 16)}...?`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/parse`, {
            method: 'POST'
        });
        
        if (response.ok) {
            alert('Parse triggered successfully');
        } else {
            alert('Failed to trigger parse');
        }
    } catch (error) {
        console.error('Error triggering parse:', error);
        alert('Error triggering parse');
    }
}

// Delete user
async function deleteUser(secretStr) {
    if (!confirm(`Are you sure you want to delete user ${secretStr.substring(0, 16)}...?`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('User deleted successfully');
            loadUsers();
        } else {
            alert('Failed to delete user');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        alert('Error deleting user');
    }
}

// Load system info
async function loadSystem() {
    const container = document.getElementById('systemInfo');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const [healthResponse, jobsResponse] = await Promise.all([
            apiFetch(`${API_BASE}/health`),
            apiFetch(`${API_BASE}/scheduler/jobs`)
        ]);
        
        let html = '<h6>System Health</h6>';
        
        if (healthResponse.ok) {
            const health = await healthResponse.json();
            html += '<div class="mb-4">';
            for (const [check, data] of Object.entries(health.checks || {})) {
                const statusColor = {
                    'healthy': 'success',
                    'degraded': 'warning',
                    'unhealthy': 'danger'
                }[data.status] || 'secondary';
                html += `<div class="mb-2"><strong>${check}:</strong> <span class="badge bg-${statusColor}">${data.status}</span></div>`;
            }
            html += '</div>';
        }
        
        html += '<h6>Scheduler Jobs</h6>';
        if (jobsResponse.ok) {
            const jobsData = await jobsResponse.json();
            if (jobsData.jobs && jobsData.jobs.length > 0) {
                html += '<ul class="list-group">';
                jobsData.jobs.forEach(job => {
                    html += `<li class="list-group-item">
                        <strong>${job.name || job.id}</strong><br>
                        <small class="text-muted">Next run: ${job.next_run_time || 'N/A'}</small>
                    </li>`;
                });
                html += '</ul>';
            } else {
                html += '<p class="text-muted">No scheduled jobs</p>';
            }
        }
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading system info:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading system information</div>';
    }
}

// Load logs
async function loadLogs() {
    const container = document.getElementById('logsTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const response = await apiFetch(`${API_BASE}/logs?limit=100`);
        
        if (response.ok) {
            const data = await response.json();
            displayLogs(data.logs || []);
        } else {
            container.innerHTML = '<div class="alert alert-danger">Failed to load logs</div>';
        }
    } catch (error) {
        console.error('Error loading logs:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading logs</div>';
    }
}

// Display logs
function displayLogs(logs) {
    const container = document.getElementById('logsTable');
    
    if (logs.length === 0) {
        container.innerHTML = '<p class="text-muted">No logs found</p>';
        return;
    }
    
    let html = '<table class="table table-sm table-hover"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th></tr></thead><tbody>';
    
    logs.forEach(log => {
        const time = new Date(log.timestamp).toLocaleString();
        html += `
            <tr>
                <td>${time}</td>
                <td>${log.username}</td>
                <td>${log.action}</td>
                <td>${log.resource || '-'}</td>
            </tr>
        `;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

// Handle password change
async function handlePasswordChange(e) {
    e.preventDefault();
    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const errorDiv = document.getElementById('passwordError');
    const successDiv = document.getElementById('passwordSuccess');
    
    errorDiv.classList.add('hidden');
    successDiv.classList.add('hidden');
    
    // Validate passwords match
    if (newPassword !== confirmPassword) {
        errorDiv.textContent = 'New passwords do not match';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    // Validate password length
    if (newPassword.length < 8) {
        errorDiv.textContent = 'New password must be at least 8 characters long';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/change-password`, {
            method: 'POST',
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });
        
        if (response.ok) {
            successDiv.textContent = 'Password changed successfully!';
            successDiv.classList.remove('hidden');
            document.getElementById('changePasswordForm').reset();
        } else {
            const error = await response.json();
            errorDiv.textContent = error.detail || 'Failed to change password';
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

// Load settings page
async function loadSettings() {
    // Load account info
    const container = document.getElementById('accountInfo');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const response = await apiFetch(`${API_BASE}/me`);
        
        if (response.ok) {
            const admin = await response.json();
            container.innerHTML = `
                <div class="mb-2"><strong>Username:</strong> ${admin.username}</div>
                <div class="mb-2"><strong>Role:</strong> <span class="badge bg-secondary">${admin.role}</span></div>
                <div class="mb-2"><strong>Created:</strong> ${admin.created_at ? new Date(admin.created_at).toLocaleString() : 'N/A'}</div>
                <div class="mb-2"><strong>Last Login:</strong> ${admin.last_login ? new Date(admin.last_login).toLocaleString() : 'Never'}</div>
            `;
        } else {
            container.innerHTML = '<div class="alert alert-danger">Failed to load account information</div>';
        }
    } catch (error) {
        console.error('Error loading settings:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading account information</div>';
    }
}

// Load channels
async function loadChannels() {
    const container = document.getElementById('channelsTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const search = document.getElementById('channelSearch').value;
        const response = await apiFetch(`${API_BASE}/channels?per_page=100${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (response.ok) {
            const data = await response.json();
            displayChannels(data.channels || [], data.pagination || {});
        } else {
            container.innerHTML = '<div class="alert alert-danger">Failed to load channels</div>';
        }
    } catch (error) {
        console.error('Error loading channels:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading channels</div>';
    }
}

// Display channels table
function displayChannels(channels, pagination) {
    const container = document.getElementById('channelsTable');
    
    if (channels.length === 0) {
        container.innerHTML = '<p class="text-muted">No channels found</p>';
        return;
    }
    
    let html = `
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>Channel Name</th>
                    <th>Group</th>
                    <th>User</th>
                    <th>Logo</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    channels.forEach(channel => {
        const userStr = channel.secret_str ? channel.secret_str.substring(0, 16) + '...' : 'Unknown';
        html += `
            <tr>
                <td><strong>${channel.tvg_name || channel.tvg_id}</strong></td>
                <td><span class="badge bg-secondary">${channel.group_title || 'N/A'}</span></td>
                <td><code>${userStr}</code></td>
                <td>${channel.tvg_logo ? `<img src="${channel.tvg_logo}" alt="Logo" style="max-height: 30px;">` : 'N/A'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    if (pagination.pages > 1) {
        html += `
            <nav>
                <ul class="pagination justify-content-center">
                    <li class="page-item ${pagination.page === 1 ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadChannelsPage(${pagination.page - 1}); return false;">Previous</a>
                    </li>
                    <li class="page-item active">
                        <span class="page-link">Page ${pagination.page} of ${pagination.pages}</span>
                    </li>
                    <li class="page-item ${pagination.page >= pagination.pages ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadChannelsPage(${pagination.page + 1}); return false;">Next</a>
                    </li>
                </ul>
            </nav>
        `;
    }
    
    container.innerHTML = html;
}

// Load channels page
function loadChannelsPage(page) {
    loadChannels();
}

// Load events
async function loadEvents() {
    const container = document.getElementById('eventsTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const search = document.getElementById('eventSearch').value;
        const response = await apiFetch(`${API_BASE}/events?per_page=100${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
        if (response.ok) {
            const data = await response.json();
            displayEvents(data.events || [], data.pagination || {});
        } else {
            container.innerHTML = '<div class="alert alert-danger">Failed to load events</div>';
        }
    } catch (error) {
        console.error('Error loading events:', error);
        container.innerHTML = '<div class="alert alert-danger">Error loading events</div>';
    }
}

// Display events table
function displayEvents(events, pagination) {
    const container = document.getElementById('eventsTable');
    
    if (events.length === 0) {
        container.innerHTML = '<p class="text-muted">No events found</p>';
        return;
    }
    
    let html = `
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>Event Title</th>
                    <th>Sport</th>
                    <th>User</th>
                    <th>Date/Time</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    events.forEach(event => {
        const userStr = event.secret_str ? event.secret_str.substring(0, 16) + '...' : 'Unknown';
        const eventTitle = event.event_title || 'N/A';
        const eventSport = event.event_sport || 'N/A';
        const eventDateTime = event.event_datetime_full || 'N/A';
        
        html += `
            <tr>
                <td><strong>${eventTitle}</strong></td>
                <td><span class="badge bg-info">${eventSport}</span></td>
                <td><code>${userStr}</code></td>
                <td>${eventDateTime}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    if (pagination.pages > 1) {
        html += `
            <nav>
                <ul class="pagination justify-content-center">
                    <li class="page-item ${pagination.page === 1 ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadEventsPage(${pagination.page - 1}); return false;">Previous</a>
                    </li>
                    <li class="page-item active">
                        <span class="page-link">Page ${pagination.page} of ${pagination.pages}</span>
                    </li>
                    <li class="page-item ${pagination.page >= pagination.pages ? 'disabled' : ''}">
                        <a class="page-link" href="#" onclick="loadEventsPage(${pagination.page + 1}); return false;">Next</a>
                    </li>
                </ul>
            </nav>
        `;
    }
    
    container.innerHTML = html;
}

// Load events page
function loadEventsPage(page) {
    loadEvents();
}

// Make functions globally available
window.viewUser = viewUser;
window.deleteUser = deleteUser;
window.loadUsersPage = loadUsersPage;
window.copyToClipboard = copyToClipboard;
window.loadChannelsPage = loadChannelsPage;
window.loadEventsPage = loadEventsPage;
