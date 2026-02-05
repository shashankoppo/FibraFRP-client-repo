# ELSX Client Restrictions - Secret Access System

## Overview

This module implements a sophisticated access control system that completely hides the Odoo Apps menu from all users (including administrators) and provides access only through a secret URL.

## Features

### 🔒 Secret URL Access
- **Complete Menu Hiding**: Apps menu is hidden from ALL users, including admin
- **Secret URL Only**: Access Apps module ONLY via `/action-39`
- **Multi-Layer Protection**: 
  - Menu-level restrictions (XML)
  - Client-side validation (JavaScript)
  - Server-side validation (Python Controller)

### 🚀 Auto-Dependency Management
- **Auto-Install Dependencies**: Automatically installs missing module dependencies
- **Auto-Upgrade**: Automatically upgrades modules when updates are available
- **Auto-Fetch Updates**: Fetches module list updates automatically
- **No Restrictions**: Full access to all installed modules without limitations

### 🛡️ Security Features
- Session-based validation
- Referer checking
- Access logging
- No group-based access (menu is hidden from everyone)

## How to Access Apps Module

### For Your Coding Team

To access the Apps module, use this URL:

```
http://localhost:8069/action-39
```

Or for production:

```
https://your-domain.com/action-39
```

**Important**: 
- This is the ONLY way to access the Apps menu
- Even admin users cannot access it through normal navigation
- The URL must be kept confidential to your coding team only

## Installation

1. The module is set to `auto_install: True`, so it will install automatically
2. After installation, restart the Odoo server
3. The Apps menu will be immediately hidden from all users
4. Access it via `/action-39`

## Module Management

### Installing New Modules

1. Navigate to `/action-39`
2. Search for the module you want to install
3. Click "Install"
4. The system will automatically:
   - Identify all dependencies
   - Install missing dependencies
   - Upgrade existing dependencies if needed

### Updating Modules

1. Navigate to `/action-39`
2. Click "Update Apps List"
3. The system will automatically:
   - Fetch latest module information
   - Identify modules that need upgrading
   - Auto-upgrade them

### No Restrictions

Once you access the Apps module via `/action-39`:
- All modules are available without restrictions
- All features are enabled
- Full import/export capabilities
- Complete module management

## Technical Details

### Architecture

```
┌─────────────────────────────────────────┐
│         User Attempts Access            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│      Menu Level (XML Security)          │
│   - Apps menu hidden from all groups    │
│   - No users in access group            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│    Client Side (JavaScript Service)     │
│   - Intercepts action requests          │
│   - Validates session storage           │
│   - Checks URL referer                  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│    Server Side (Python Controller)      │
│   - Validates /action-39 access         │
│   - Logs access attempts                │
│   - Redirects to Apps action            │
└─────────────────────────────────────────┘
```

### Files Structure

```
elsx_client_restrictions/
├── __init__.py                          # Main init
├── __manifest__.py                      # Module manifest
├── controllers/
│   ├── __init__.py
│   └── main.py                          # Secret URL controller
├── models/
│   ├── __init__.py
│   └── ir_module.py                     # Auto-dependency management
├── security/
│   └── security_groups.xml              # Empty security group
├── views/
│   ├── menu_restrictions.xml            # Menu hiding
│   └── assets.xml                       # JS assets loading
└── static/
    └── src/
        └── js/
            └── secret_apps_access.js    # Client-side validation
```

### Key Components

1. **Security Group** (`security_groups.xml`):
   - Creates an empty group with no users
   - Apps menu is assigned to this group
   - Result: Menu is invisible to everyone

2. **Menu Restrictions** (`menu_restrictions.xml`):
   - Hides `base.menu_management`
   - Hides `base.menu_apps`
   - Hides theme installation menu

3. **Controller** (`controllers/main.py`):
   - Route: `/action-39`
   - Validates access
   - Logs attempts
   - Redirects to Apps action

4. **JavaScript Service** (`secret_apps_access.js`):
   - Intercepts `doAction` calls
   - Validates session storage
   - Blocks unauthorized access
   - Shows notifications

5. **Module Extension** (`ir_module.py`):
   - Auto-installs dependencies
   - Auto-upgrades modules
   - Removes access restrictions
   - Enables full functionality

## Security Considerations

### What's Protected
✅ Apps menu completely hidden from UI
✅ Direct action access blocked
✅ Menu navigation blocked
✅ Developer mode doesn't reveal menu

### What's Accessible via /action-39
✅ Full Apps module functionality
✅ Install/Uninstall modules
✅ Update module list
✅ Configure modules
✅ Import/Export data
✅ All module features

### Access Logging

All access attempts are logged:
```python
_logger.info('Secret access to Apps module via /action-39 by user: %s', request.env.user.login)
```

Check logs at:
```
/var/log/odoo/odoo-server.log
```

## Troubleshooting

### Apps Menu Still Visible
1. Restart Odoo server
2. Clear browser cache
3. Update module list
4. Verify module is installed

### Cannot Access via /action-39
1. Check if you're logged in
2. Verify URL is correct: `http://localhost:8069/action-39`
3. Check server logs for errors
4. Ensure module is installed and upgraded

### Dependencies Not Auto-Installing
1. Check server logs for errors
2. Verify module has proper `__manifest__.py`
3. Ensure dependencies are available in addons path
4. Try manual installation first

## Configuration

### Change Secret URL

To change the secret URL from `/action-39` to something else:

1. Edit `controllers/main.py`:
```python
@http.route('/your-secret-url', type='http', auth='user', website=False)
```

2. Edit `static/src/js/secret_apps_access.js`:
```javascript
const hasSecretAccess = currentUrl.includes('/your-secret-url') || ...
```

3. Restart Odoo server

### Disable Auto-Install

Edit `__manifest__.py`:
```python
'auto_install': False,
```

## Best Practices

1. **Keep URL Secret**: Only share `/action-39` with your coding team
2. **Use HTTPS**: In production, always use HTTPS
3. **Monitor Logs**: Regularly check access logs
4. **Backup Before Updates**: Always backup before module updates
5. **Test in Staging**: Test module installations in staging first

## Support

For issues or questions:
- Check server logs: `/var/log/odoo/odoo-server.log`
- Enable debug mode: Add `--log-level=debug` to Odoo startup
- Review this README thoroughly

## License

LGPL-3

## Author

ELSX Evolution Engine
https://elsx-erp.com
