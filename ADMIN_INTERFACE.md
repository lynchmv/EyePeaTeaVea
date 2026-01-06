# Admin Interface Documentation

## Overview

The Admin Interface provides a comprehensive dashboard for managing the EyePeaTeaVea multi-user IPTV addon service. It includes user management, system monitoring, and administrative controls.

## Features

### Authentication & Authorization
- **Role-based access control**: Three roles available:
  - `viewer`: Read-only access to view users and system status
  - `admin`: Can manage users, trigger operations, clear caches
  - `super_admin`: Full access including system configuration
- **Session management**: Secure cookie-based sessions with 24-hour expiration
- **Default admin**: On first run, creates default admin user:
  - Username: `admin`
  - Password: `admin`
  - **⚠️ IMPORTANT: Change the default password immediately!**

### User Management
- **List users**: View all users with pagination and search
- **User details**: View detailed user configuration and statistics
- **Edit users**: Update user configurations (M3U sources, schedule, etc.)
- **Delete users**: Remove users and all associated data
- **Manual operations**: 
  - Trigger manual M3U parse
  - Clear user cache

### System Monitoring
- **Dashboard**: Overview with key statistics
  - Total users, channels, events
  - Active scheduler jobs
  - System health indicators
- **System health**: Detailed health checks for Redis and Scheduler
- **Scheduler status**: View all scheduled jobs and their next run times
- **Audit logs**: View admin actions and system events

## Access

### Web Interface
Access the admin dashboard at: `http://your-host/admin/`

### API Endpoints
All admin endpoints are prefixed with `/admin`:

#### Authentication
- `POST /admin/login` - Admin login
- `POST /admin/logout` - Admin logout
- `GET /admin/me` - Get current admin user info

#### User Management
- `GET /admin/users` - List all users (paginated, searchable)
- `GET /admin/users/{secret_str}` - Get user details
- `PUT /admin/users/{secret_str}` - Update user configuration
- `DELETE /admin/users/{secret_str}` - Delete user
- `POST /admin/users/{secret_str}/parse` - Trigger manual parse
- `POST /admin/users/{secret_str}/cache/clear` - Clear user cache

#### System Monitoring
- `GET /admin/stats` - Get system statistics
- `GET /admin/health` - Get detailed system health
- `GET /admin/scheduler/jobs` - Get scheduler jobs
- `GET /admin/logs` - Get audit logs

## Security Considerations

1. **Default Credentials**: The default admin password should be changed immediately after first login
2. **HTTPS**: In production, ensure HTTPS is enabled for secure cookie transmission
3. **IP Allowlist**: Consider implementing IP allowlist for admin access (future enhancement)
4. **Session Security**: Sessions use HTTP-only cookies with secure flag (enable in production)
5. **Audit Logging**: All admin actions are logged for security auditing

## Creating Additional Admin Users

Currently, admin users must be created manually via Redis or by adding code to create them. Future enhancements could include:
- Admin user management UI
- Password reset functionality
- Two-factor authentication

To create an admin user programmatically:

```python
from src.redis_store import RedisStore
from src.utils import hash_password
from datetime import datetime

redis_store = RedisStore("redis://localhost:6379/0")

admin_user = {
    "username": "newadmin",
    "password_hash": hash_password("secure_password"),
    "role": "admin",  # or "super_admin" or "viewer"
    "created_at": datetime.now().isoformat(),
    "last_login": None,
    "is_active": True
}

redis_store.store_admin_user("newadmin", admin_user)
```

## File Structure

```
admin/
├── index.html          # Admin dashboard HTML
└── admin.js            # Admin dashboard JavaScript

src/
├── admin.py            # Admin API endpoints
├── admin_auth.py       # Authentication and authorization utilities
├── models.py           # Admin models (AdminUser, AdminSession, etc.)
└── redis_store.py      # Admin data storage methods
```

## Future Enhancements

- Admin user management UI
- Real-time updates via WebSockets
- Advanced analytics and reporting
- Export/import functionality
- Bulk operations
- System configuration management
- Performance metrics and charts
