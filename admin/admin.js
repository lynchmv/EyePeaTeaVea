// Admin Dashboard JavaScript

const API_BASE = '/admin';
const ASSETS_BASE = '/admin-assets';

// Notification system using Bootstrap toasts
function showNotification(message, type = 'info', duration = 5000) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        // Fallback to console if toast container doesn't exist
        console.log(`[${type.toUpperCase()}] ${message}`);
        return;
    }
    
    const toastId = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const bgClass = {
        'success': 'bg-success',
        'error': 'bg-danger',
        'warning': 'bg-warning',
        'info': 'bg-info'
    }[type] || 'bg-info';
    
    const icon = {
        'success': 'bi-check-circle-fill',
        'error': 'bi-exclamation-triangle-fill',
        'warning': 'bi-exclamation-triangle-fill',
        'info': 'bi-info-circle-fill'
    }[type] || 'bi-info-circle-fill';
    
    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true" data-bs-autohide="true" data-bs-delay="${duration}">
            <div class="toast-header ${bgClass} text-white">
                <i class="bi ${icon} me-2"></i>
                <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message.replace(/\n/g, '<br>')}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

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
let currentChannelsPage = 1;
let currentEventsPage = 1;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    checkAuth();
    setupEventListeners();
});

// Theme management
function initTheme() {
    const savedTheme = localStorage.getItem('adminTheme') || 'light';
    setTheme(savedTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('adminTheme', theme);
    
    const themeIcon = document.getElementById('themeIcon');
    if (themeIcon) {
        if (theme === 'dark') {
            themeIcon.className = 'bi bi-sun-fill';
            themeIcon.parentElement.title = 'Switch to light mode';
        } else {
            themeIcon.className = 'bi bi-moon-fill';
            themeIcon.parentElement.title = 'Switch to dark mode';
        }
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
}

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
        loadChannels(1); // Reset to page 1 on search
    });
    document.getElementById('channelSearch').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadChannels(1); // Reset to page 1 on search
        }
    });
    
    // Event search
    document.getElementById('eventSearchBtn').addEventListener('click', () => {
        loadEvents(1); // Reset to page 1 on search
    });
    document.getElementById('eventSearch').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadEvents(1); // Reset to page 1 on search
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
    
    // Theme toggle
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
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
        const newUrl = `/dashboard/${page === 'dashboard' ? '' : page}`;
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
                currentChannelsPage = 1;
                loadChannels();
                break;
            case 'events':
                currentEventsPage = 1;
                loadEvents();
                break;
        }
    }
}

// Handle browser back/forward buttons
window.addEventListener('popstate', (event) => {
    if (event.state?.page === 'userDetail' && event.state?.secretStr) {
        navigateToUserDetail(event.state.secretStr);
    } else {
        const page = event.state?.page || getPageFromPath();
        navigateToPage(page, false);
    }
});

// Get page from current path
function getPageFromPath() {
    const path = window.location.pathname;
    if (path === '/dashboard' || path === '/dashboard/') {
        return 'dashboard';
    }
    
    // Check if it's a user detail page (e.g., /dashboard/users/{secret_str})
    const userDetailMatch = path.match(/^\/dashboard\/users\/(.+)$/);
    if (userDetailMatch) {
        const secretStr = userDetailMatch[1];
        navigateToUserDetail(secretStr);
        return 'userDetail';
    }
    
    const match = path.match(/^\/dashboard\/([^/]+)/);
    if (match) {
        const page = match[1];
        // Validate page exists
        const validPages = ['dashboard', 'users', 'channels', 'events', 'system', 'logs', 'settings'];
        if (validPages.includes(page)) {
            return page;
        }
    }
    
    // Fallback: check if it's /admin (for backwards compatibility)
    if (path === '/admin' || path === '/admin/') {
        return 'dashboard';
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

// View user details - navigate to user detail page
function viewUser(secretStr) {
    // Navigate to user detail page with secret_str in URL
    const newUrl = `/dashboard/users/${secretStr}`;
    window.history.pushState({ page: 'userDetail', secretStr: secretStr }, '', newUrl);
    navigateToUserDetail(secretStr);
}

// Navigate to user detail page
async function navigateToUserDetail(secretStr) {
    currentPage = 'userDetail';
    
    // Update sidebar - highlight users menu item
    document.querySelectorAll('.sidebar-menu a').forEach(link => {
        link.classList.remove('active');
        if (link.dataset.page === 'users') {
            link.classList.add('active');
        }
    });
    
    // Hide all pages
    document.querySelectorAll('.page-content').forEach(p => {
        p.classList.add('hidden');
    });
    
    // Show user detail page
    const pageElement = document.getElementById('userDetailPage');
    if (pageElement) {
        pageElement.classList.remove('hidden');
        document.getElementById('pageTitle').textContent = `User: ${secretStr.substring(0, 16)}...`;
        
        // Load user details
        await loadUserDetail(secretStr);
    }
}

// Load user detail content
async function loadUserDetail(secretStr) {
    const content = document.getElementById('userDetailContent');
    content.innerHTML = '<div class="loading"><div class="spinner-border text-primary" role="status"></div></div>';
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}`);
        
        if (response.ok) {
            const user = await response.json();
            displayUserDetail(user);
        } else {
            content.innerHTML = '<div class="alert alert-danger">Failed to load user details</div>';
        }
    } catch (error) {
        console.error('Error loading user details:', error);
        content.innerHTML = '<div class="alert alert-danger">Error loading user details</div>';
    }
}

// Display user detail on page
function displayUserDetail(user) {
    const content = document.getElementById('userDetailContent');
    
    let html = `
        <div class="table-container mb-3">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>User Details</h5>
                ${currentUser && currentUser.role !== 'viewer' ? `
                    <div>
                        <button class="btn btn-primary me-2" onclick="triggerUserParse('${user.secret_str}')">
                            <i class="bi bi-play-circle"></i> Trigger Parse
                        </button>
                        <button class="btn btn-warning me-2" onclick="clearUserCache('${user.secret_str}')">
                            <i class="bi bi-arrow-clockwise"></i> Clear Cache
                        </button>
                        <button class="btn btn-danger" onclick="deleteUser('${user.secret_str}')">
                            <i class="bi bi-trash"></i> Delete User
                        </button>
                    </div>
                ` : ''}
            </div>
            
            <div class="mb-3">
                <h6>Configuration</h6>
                <table class="table table-sm">
                    <tr>
                        <th width="30%">Secret String:</th>
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
    
    user.configuration.m3u_sources.forEach((source) => {
        html += `<li class="list-group-item"><small><code>${source}</code></small></li>`;
    });
    
    html += `
                </ul>
            </div>
            
            <div class="mb-3">
                <h6>Statistics</h6>
                <div class="row">
                    <div class="col-md-3">
                        <div class="card text-center">
                            <div class="card-body">
                                <h3 class="card-title">${user.statistics.channel_count}</h3>
                                <p class="card-text text-muted">Channels</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-center">
                            <div class="card-body">
                                <h3 class="card-title">${user.statistics.event_count}</h3>
                                <p class="card-text text-muted">Events</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-center">
                            <div class="card-body">
                                <h3 class="card-title">${user.statistics.epg_channel_count}</h3>
                                <p class="card-text text-muted">EPG Channels</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-center">
                            <div class="card-body">
                                <h3 class="card-title">${user.statistics.m3u_source_count}</h3>
                                <p class="card-text text-muted">M3U Sources</p>
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
        </div>
    `;
    
    // Add parse history section
    html += `
        <div class="table-container mb-3">
            <h6>Parse History</h6>
    `;
    
    if (user.parse_history && user.parse_history.length > 0) {
        html += `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Status</th>
                            <th>Channels</th>
                            <th>Sources Processed</th>
                            <th>Errors</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        user.parse_history.forEach(parse => {
            const time = new Date(parse.timestamp).toLocaleString();
            const statusBadge = parse.success 
                ? '<span class="badge bg-success">Success</span>'
                : '<span class="badge bg-danger">Failed</span>';
            const errorCount = parse.error_count || 0;
            const sourcesProcessed = parse.sources_processed || 0;
            const sourcesFailed = parse.sources_failed || 0;
            
            html += `
                <tr>
                    <td>${time}</td>
                    <td>${statusBadge}</td>
                    <td>${parse.channel_count || 0}</td>
                    <td>${sourcesProcessed} (${sourcesFailed} failed)</td>
                    <td>${errorCount > 0 ? `<span class="text-danger fw-bold">${errorCount}</span>` : '<span class="text-muted">0</span>'}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    } else {
        html += '<p class="text-muted">No parse history available yet.</p>';
    }
    
    html += `</div>`;
    
    // Add recent errors section
    html += `
        <div class="table-container mb-3">
            <h6>Recent Errors</h6>
    `;
    
    if (user.recent_errors && user.recent_errors.length > 0) {
        html += `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Type</th>
                            <th>Message</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        user.recent_errors.forEach(error => {
            const time = new Date(error.timestamp).toLocaleString();
            const errorType = error.error_type || 'error';
            const message = error.message || '';
            
            html += `
                <tr>
                    <td><small>${time}</small></td>
                    <td><span class="badge bg-warning">${errorType}</span></td>
                    <td><small class="font-monospace">${message}</small></td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    } else {
        html += '<p class="text-muted">No recent errors.</p>';
    }
    
    html += `</div>`;
    
    // Add logo overrides section
    html += `
        <div class="table-container mb-3">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6>Logo Overrides</h6>
                ${currentUser && currentUser.role !== 'viewer' ? `
                    <button class="btn btn-sm btn-primary" onclick="showAddLogoOverrideModal('${user.secret_str}')">
                        <i class="bi bi-plus-circle"></i> Add Override
                    </button>
                ` : ''}
            </div>
            <div id="logoOverridesContent">
                <div class="loading">
                    <div class="spinner-border text-primary" role="status"></div>
                </div>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
    
    // Load logo overrides
    loadLogoOverrides(user.secret_str);
}

// Load logo overrides for a user
async function loadLogoOverrides(secretStr) {
    currentLogoOverrideSecretStr = secretStr; // Store for use by selectChannelForOverride
    const container = document.getElementById('logoOverridesContent');
    if (!container) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/logo-overrides`);
        
        if (response.ok) {
            const data = await response.json();
            displayLogoOverrides(secretStr, data.overrides || {}, data.available_channels || []);
        } else {
            container.innerHTML = '<p class="text-muted">Failed to load logo overrides</p>';
        }
    } catch (error) {
        console.error('Error loading logo overrides:', error);
        container.innerHTML = '<p class="text-muted">Error loading logo overrides</p>';
    }
}

// Display logo overrides
function displayLogoOverrides(secretStr, overrides, availableChannels) {
    const container = document.getElementById('logoOverridesContent');
    if (!container) return;
    
    // overrides is now an array, not an object
    const overrideList = Array.isArray(overrides) ? overrides : Object.entries(overrides).map(([tvg_id, data]) => {
        // Handle legacy format
        if (typeof data === 'string') {
            return { tvg_id, logo_url: data, is_regex: false };
        }
        return { tvg_id, ...data };
    });
    
    let html = '';
    
    // Add export/import buttons if user has admin permissions
    // Check currentUser or try to get it from the page context
    const userRole = currentUser ? currentUser.role : null;
    if (userRole && userRole !== 'viewer') {
        html += `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6>Logo Overrides</h6>
                <div>
                    <button class="btn btn-sm btn-outline-primary me-2" onclick="exportLogoOverrides('${secretStr}')">
                        <i class="bi bi-download"></i> Export
                    </button>
                    <button class="btn btn-sm btn-outline-success" onclick="showImportLogoOverridesModal('${secretStr}')">
                        <i class="bi bi-upload"></i> Import
                    </button>
                </div>
            </div>
        `;
    } else {
        html += '<h6>Logo Overrides</h6>';
    }
    
    if (overrideList.length === 0) {
        html += '<p class="text-muted mb-3">No logo overrides configured.</p>';
    } else {
        html += `
            <div class="table-responsive mb-3">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Channel ID / Pattern</th>
                            <th>Channel Name</th>
                            <th>Type</th>
                            <th>Logo URL</th>
                            <th>Preview</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        overrideList.forEach(override => {
            const tvg_id = override.tvg_id;
            const logo_url = override.logo_url || '';
            const is_regex = override.is_regex || false;
            
            // Find channel name from available channels (only for exact matches)
            const channel = availableChannels.find(c => c.tvg_id === tvg_id);
            const channelName = channel ? channel.tvg_name : (is_regex ? '(Regex Pattern)' : tvg_id);
            
            // Escape single quotes in tvg_id for onclick handler
            const escapedTvgId = tvg_id.replace(/'/g, "\\'");
            
            html += `
                <tr>
                    <td><code>${tvg_id}</code>${is_regex ? ' <span class="badge bg-info">REGEX</span>' : ''}</td>
                    <td>${channelName}</td>
                    <td>${is_regex ? '<span class="badge bg-info">Regex Pattern</span>' : '<span class="badge bg-secondary">Exact Match</span>'}</td>
                    <td><small class="font-monospace">${logo_url.length > 50 ? logo_url.substring(0, 50) + '...' : logo_url}</small></td>
                    <td><img src="${logo_url}" alt="Logo" style="max-height: 40px; max-width: 80px;" onerror="this.style.display='none'"></td>
                    <td>
                        ${currentUser && currentUser.role !== 'viewer' ? `
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteLogoOverride('${secretStr}', '${escapedTvgId}')">
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
            </div>
        `;
    }
    
    // Add channel selector helper
    if (availableChannels.length > 0 && currentUser && currentUser.role !== 'viewer') {
        html += `
            <div class="mb-3">
                <h6>Quick Add from Channel List</h6>
                <div class="input-group mb-2">
                    <select class="form-select" id="channelSelector">
                        <option value="">Select a channel...</option>
        `;
        
        availableChannels.forEach(channel => {
            const selected = channel.has_override ? ' (has override)' : '';
            html += `<option value="${channel.tvg_id}">${channel.tvg_name} (${channel.tvg_id})${selected}</option>`;
        });
        
        html += `
                    </select>
                    <button class="btn btn-outline-secondary" type="button" onclick="selectChannelForOverride()">
                        Use This Channel
                    </button>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Select channel for override (populate modal form)
function selectChannelForOverride() {
    const selector = document.getElementById('channelSelector');
    const tvgId = selector.value;
    if (!tvgId) {
        showNotification('Please select a channel first', 'warning');
        return;
    }
    
    // Ensure we have a secretStr
    if (!currentLogoOverrideSecretStr) {
        showNotification('Error: User context not found. Please refresh the page.', 'error');
        return;
    }
    
    // Open the modal if not already open
    const modalElement = document.getElementById('logoOverrideModal');
    const modal = bootstrap.Modal.getInstance(modalElement);
    if (!modal || !modal._isShown) {
        showAddLogoOverrideModal(currentLogoOverrideSecretStr);
    }
    
    // Populate the form fields
    document.getElementById('overrideTvgId').value = tvgId;
    document.getElementById('overrideIsRegex').checked = false; // Default to exact match when selecting from channel list
    // Clear any previous URL and focus on URL field
    document.getElementById('overrideLogoUrl').value = '';
    document.getElementById('overrideLogoUrl').focus();
}

// Current secret_str for logo override operations
let currentLogoOverrideSecretStr = null;

// Show add logo override modal
function showAddLogoOverrideModal(secretStr) {
    currentLogoOverrideSecretStr = secretStr;
    const modal = new bootstrap.Modal(document.getElementById('logoOverrideModal'));
    document.getElementById('logoOverrideForm').reset();
    document.getElementById('overrideIsRegex').checked = false;
    document.getElementById('logoOverrideError').classList.add('hidden');
    document.getElementById('logoOverrideSuccess').classList.add('hidden');
    modal.show();
}

// Submit logo override
function submitLogoOverride() {
    const tvgId = document.getElementById('overrideTvgId').value.trim();
    const logoUrl = document.getElementById('overrideLogoUrl').value.trim();
    const isRegex = document.getElementById('overrideIsRegex').checked;
    const errorDiv = document.getElementById('logoOverrideError');
    const successDiv = document.getElementById('logoOverrideSuccess');
    
    errorDiv.classList.add('hidden');
    successDiv.classList.remove('hidden');
    
    if (!tvgId || !logoUrl) {
        errorDiv.textContent = 'Please fill in all fields';
        errorDiv.classList.remove('hidden');
        successDiv.classList.add('hidden');
        return;
    }
    
    // Validate regex if is_regex is checked
    if (isRegex) {
        try {
            new RegExp(tvgId);
        } catch (e) {
            errorDiv.textContent = `Invalid regex pattern: ${e.message}`;
            errorDiv.classList.remove('hidden');
            successDiv.classList.add('hidden');
            return;
        }
    }
    
    createLogoOverride(currentLogoOverrideSecretStr, tvgId, logoUrl, isRegex);
}

// Create logo override
async function createLogoOverride(secretStr, tvgId, logoUrl, isRegex = false) {
    const errorDiv = document.getElementById('logoOverrideError');
    const successDiv = document.getElementById('logoOverrideSuccess');
    
    errorDiv.classList.add('hidden');
    successDiv.classList.add('hidden');
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/logo-overrides`, {
            method: 'POST',
            body: JSON.stringify({
                tvg_id: tvgId,
                logo_url: logoUrl,
                is_regex: isRegex
            })
        });
        
        if (response.ok) {
            successDiv.textContent = 'Logo override created successfully!';
            successDiv.classList.remove('hidden');
            
            // Close modal after a short delay
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById('logoOverrideModal'));
                if (modal) modal.hide();
            }, 1500);
            
            // Reload logo overrides and user detail
            loadLogoOverrides(secretStr);
            setTimeout(() => loadUserDetail(secretStr), 500);
        } else {
            const error = await response.json();
            errorDiv.textContent = error.detail || 'Failed to create logo override';
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error creating logo override:', error);
        errorDiv.textContent = 'Error creating logo override. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

// Delete logo override
async function deleteLogoOverride(secretStr, tvgId) {
    if (!confirm(`Delete logo override for channel "${tvgId}"?`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/logo-overrides/${encodeURIComponent(tvgId)}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Logo override deleted successfully', 'success');
            loadLogoOverrides(secretStr);
            // Reload user detail to refresh
            loadUserDetail(secretStr);
        } else {
            const error = await response.json();
            showNotification(`Failed to delete logo override: ${error.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting logo override:', error);
        showNotification('Error deleting logo override', 'error');
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
            showNotification('Parse triggered successfully. The page will refresh in a moment.', 'success');
            // Reload user details after a short delay
            setTimeout(() => {
                loadUserDetail(secretStr);
            }, 2000);
        } else {
            const error = await response.json();
            showNotification(`Failed to trigger parse: ${error.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error triggering parse:', error);
        showNotification('Error triggering parse', 'error');
    }
}

// Export logo overrides
async function exportLogoOverrides(secretStr) {
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/logo-overrides/export`);
        
        if (response.ok) {
            const data = await response.json();
            
            // Create a blob and download it
            const jsonStr = JSON.stringify(data, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logo-overrides-${secretStr.substring(0, 8)}-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            showNotification(`Exported ${data.count} logo override(s) successfully!`, 'success');
        } else {
            const error = await response.json();
            showNotification(`Failed to export logo overrides: ${error.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error exporting logo overrides:', error);
        showNotification('Error exporting logo overrides', 'error');
    }
}

// Show import logo overrides modal
function showImportLogoOverridesModal(secretStr) {
    currentLogoOverrideSecretStr = secretStr;
    const modal = new bootstrap.Modal(document.getElementById('importLogoOverridesModal'));
    document.getElementById('importLogoOverridesForm').reset();
    document.getElementById('importLogoOverridesError').classList.add('hidden');
    document.getElementById('importLogoOverridesSuccess').classList.add('hidden');
    modal.show();
}

// Submit import logo overrides
async function submitImportLogoOverrides() {
    const fileInput = document.getElementById('importLogoOverridesFile');
    const textArea = document.getElementById('importLogoOverridesText');
    const errorDiv = document.getElementById('importLogoOverridesError');
    const successDiv = document.getElementById('importLogoOverridesSuccess');
    
    errorDiv.classList.add('hidden');
    successDiv.classList.add('hidden');
    
    let importData = null;
    
    // Check if file was uploaded
    if (fileInput.files && fileInput.files.length > 0) {
        const file = fileInput.files[0];
        try {
            const text = await file.text();
            importData = JSON.parse(text);
        } catch (e) {
            errorDiv.textContent = `Error reading file: ${e.message}`;
            errorDiv.classList.remove('hidden');
            return;
        }
    } else if (textArea.value.trim()) {
        // Use text area content
        try {
            importData = JSON.parse(textArea.value.trim());
        } catch (e) {
            errorDiv.textContent = `Invalid JSON: ${e.message}`;
            errorDiv.classList.remove('hidden');
            return;
        }
    } else {
        errorDiv.textContent = 'Please provide a JSON file or paste JSON content';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    if (!importData) {
        errorDiv.textContent = 'No import data provided';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${currentLogoOverrideSecretStr}/logo-overrides/import`, {
            method: 'POST',
            body: JSON.stringify(importData)
        });
        
        if (response.ok) {
            const data = await response.json();
            let message = `Import completed!<br>Imported: ${data.imported}<br>Updated: ${data.updated}<br>Errors: ${data.errors}`;
            if (data.error_details && data.error_details.length > 0) {
                const errorList = data.error_details.slice(0, 5).join('<br>') + (data.error_details.length > 5 ? `<br>... and ${data.error_details.length - 5} more` : '');
                message += `<br><br><strong>Errors:</strong><br><small>${errorList}</small>`;
            }
            showNotification(message, data.errors > 0 ? 'warning' : 'success', 8000);
            
            // Close modal and reload logo overrides
            const modal = bootstrap.Modal.getInstance(document.getElementById('importLogoOverridesModal'));
            modal.hide();
            loadLogoOverrides(currentLogoOverrideSecretStr);
            loadUserDetail(currentLogoOverrideSecretStr);
        } else {
            const error = await response.json();
            errorDiv.textContent = error.detail || 'Failed to import logo overrides';
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error importing logo overrides:', error);
        errorDiv.textContent = 'Error importing logo overrides. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

// Clear user image cache
async function clearUserCache(secretStr) {
    if (!confirm(`Clear all cached images for this user? This will force regeneration of all images on next request.`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}/clear-image-cache`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            showNotification(`Image cache cleared successfully!<br>Channels processed: ${data.channels_processed}<br>Deleted cache keys: ${data.deleted_keys}`, 'success');
        } else {
            const error = await response.json();
            showNotification(`Failed to clear cache: ${error.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error clearing cache:', error);
        showNotification('Error clearing cache', 'error');
    }
}

// Delete user
async function deleteUser(secretStr) {
    if (!confirm(`Are you sure you want to delete user ${secretStr.substring(0, 16)}...? This action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/users/${secretStr}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('User deleted successfully', 'success');
            // Navigate back to users list
            navigateToPage('users');
        } else {
            const error = await response.json();
            showNotification(`Failed to delete user: ${error.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showNotification('Error deleting user', 'error');
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
async function loadChannels(page = null) {
    if (page !== null) {
        currentChannelsPage = page;
    }
    const container = document.getElementById('channelsTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const search = document.getElementById('channelSearch').value;
        const response = await apiFetch(`${API_BASE}/channels?page=${currentChannelsPage}&per_page=100${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
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
    loadChannels(page);
}

// Load events
async function loadEvents(page = null) {
    if (page !== null) {
        currentEventsPage = page;
    }
    const container = document.getElementById('eventsTable');
    container.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
    
    try {
        const search = document.getElementById('eventSearch').value;
        const response = await apiFetch(`${API_BASE}/events?page=${currentEventsPage}&per_page=100${search ? `&search=${encodeURIComponent(search)}` : ''}`);
        
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
    loadEvents(page);
}

// Make functions globally available
window.viewUser = viewUser;
window.deleteUser = deleteUser;
window.loadUsersPage = loadUsersPage;
window.copyToClipboard = copyToClipboard;
window.loadChannelsPage = loadChannelsPage;
window.loadEventsPage = loadEventsPage;
window.showAddLogoOverrideModal = showAddLogoOverrideModal;
window.deleteLogoOverride = deleteLogoOverride;
window.selectChannelForOverride = selectChannelForOverride;
window.submitLogoOverride = submitLogoOverride;
window.clearUserCache = clearUserCache;
window.exportLogoOverrides = exportLogoOverrides;
window.showImportLogoOverridesModal = showImportLogoOverridesModal;
window.submitImportLogoOverrides = submitImportLogoOverrides;
