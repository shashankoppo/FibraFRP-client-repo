# Deployment Checklist

## Pre-Deployment

- [ ] Backup your database
- [ ] Backup your filestore
- [ ] Note current installed modules
- [ ] Document current admin credentials

## Deployment Steps

### 1. Upgrade the Module

```bash
# Stop Odoo server
sudo systemctl stop odoo

# Or if using manual start
# Kill the Odoo process

# Start Odoo with upgrade
./odoo-bin -c odoo.conf -u elsx_client_restrictions -d your_database_name

# Or
python3 odoo-bin -c odoo.conf -u elsx_client_restrictions -d your_database_name
```

### 2. Verify Installation

- [ ] Check server logs for errors
- [ ] Verify module is installed
- [ ] Check that Apps menu is hidden

### 3. Test Secret Access

- [ ] Navigate to `http://localhost:8069/action-39`
- [ ] Verify Apps module loads
- [ ] Test installing a module
- [ ] Test updating module list

### 4. Test Restrictions

- [ ] Log in as admin
- [ ] Verify Apps menu is NOT visible in navigation
- [ ] Enable developer mode
- [ ] Verify Apps menu is STILL not visible
- [ ] Try to access Apps through normal navigation (should fail)

### 5. Test Auto-Dependencies

- [ ] Install a module with dependencies
- [ ] Verify dependencies auto-install
- [ ] Check logs for auto-install messages

## Post-Deployment

### Verify Everything Works

- [ ] Apps menu hidden from all users
- [ ] `/action-39` provides access
- [ ] Module installation works
- [ ] Dependencies auto-install
- [ ] Module updates work
- [ ] No restrictions on module features

### Share with Team

- [ ] Share `/action-39` URL with coding team
- [ ] Share TEAM_GUIDE.md
- [ ] Emphasize confidentiality
- [ ] Set up bookmarks for team

### Monitor

- [ ] Check access logs regularly
- [ ] Monitor for unauthorized access attempts
- [ ] Verify auto-upgrades are working

## Rollback Plan

If something goes wrong:

```bash
# Stop Odoo
sudo systemctl stop odoo

# Restore database backup
psql -U odoo -d postgres -c "DROP DATABASE your_database_name;"
psql -U odoo -d postgres -c "CREATE DATABASE your_database_name;"
psql -U odoo -d your_database_name < backup.sql

# Restore filestore
rm -rf /path/to/filestore/your_database_name
cp -r /path/to/backup/filestore/your_database_name /path/to/filestore/

# Start Odoo
sudo systemctl start odoo
```

## Troubleshooting

### Apps Menu Still Visible
```bash
# Clear cache
rm -rf ~/.local/share/Odoo/sessions/*

# Restart with update
./odoo-bin -c odoo.conf -u elsx_client_restrictions -d your_database_name
```

### /action-39 Not Working
```bash
# Check if module is installed
# In Odoo shell:
./odoo-bin shell -c odoo.conf -d your_database_name

>>> env['ir.module.module'].search([('name', '=', 'elsx_client_restrictions')])
>>> # Should show the module

# Check controller is loaded
>>> env['ir.http']._get_public_methods()
>>> # Should include 'secret_apps_access'
```

### Dependencies Not Auto-Installing
```bash
# Check logs
tail -f /var/log/odoo/odoo-server.log

# Look for errors in ir_module.py
# Verify module paths are correct
```

## Success Criteria

✅ Apps menu is completely hidden from UI
✅ `/action-39` provides full access to Apps
✅ Module installation works without restrictions
✅ Dependencies auto-install
✅ Module updates auto-fetch
✅ Access is logged
✅ Team can access via secret URL
✅ Clients cannot access Apps menu

## Notes

- Keep `/action-39` URL confidential
- Monitor logs for security
- Test in staging before production
- Document any customizations

---

**Date Deployed**: _______________
**Deployed By**: _______________
**Database**: _______________
**Verified By**: _______________
