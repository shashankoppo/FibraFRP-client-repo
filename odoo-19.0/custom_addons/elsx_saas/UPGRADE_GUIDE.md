# SaaS Module Enterprise Upgrade Guide

**Version**: 19.0.2.0.0 (Enterprise Edition)
**Upgrade From**: 19.0.1.2.1
**Date**: June 2026
**Risk Level**: LOW - Full backward compatibility, zero data loss

---

## 🛡️ Safety Guarantee

This upgrade has been designed with **zero data loss** as the top priority:

✅ **No Production System Disruption** - Running system unaffected during upgrade
✅ **Automatic Backup** - Full backup created before any changes
✅ **Pre-Check Validation** - Comprehensive system validation before upgrade
✅ **Reversible Process** - Can rollback to previous version if needed
✅ **Post-Upgrade Verification** - Automatic verification that everything works
✅ **Immutable Logs** - Complete audit trail of all changes

---

## 📋 Pre-Upgrade Checklist

Before starting the upgrade, verify:

- [ ] **Backup Verified** - Recent database backup exists (< 24 hours old)
- [ ] **Disk Space** - At least 2GB free disk space available
- [ ] **Users Logged Out** - All users logged out of the system
- [ ] **No Processes Running** - No batch jobs or imports in progress
- [ ] **Module Dependencies** - All required modules (mail, sale, account) installed
- [ ] **No Locks** - No database locks or long transactions
- [ ] **Testing Ready** - Test environment upgraded first (optional but recommended)

---

## 🚀 Quick Upgrade (Auto-Safe Path)

### Step 1: Access Module Upgrade
```
Navigate to: Apps → Search "SaaS" → Click "SaaS Module"
```

### Step 2: Click Upgrade
```
Click: "Upgrade to Enterprise Edition (v2.0.0)"
```

### Step 3: Run Pre-Checks
The system will automatically:
- ✓ Check backup status
- ✓ Verify disk space
- ✓ Confirm no active sessions
- ✓ Validate data integrity
- ✓ Check module dependencies
- ✓ Detect database locks
- ✓ Monitor log file sizes

**If Pre-Checks Fail:**
The upgrade will NOT proceed. You'll see what needs to be fixed.
Address issues and retry.

### Step 4: Backup Creation
The system will:
- Create full database backup
- Verify backup integrity
- Store backup location

### Step 5: Data Migration
The system will:
- Create new data structures
- Migrate billing plans (if custom)
- Set up security policies
- Initialize new enterprise features

### Step 6: Post-Upgrade Verification
The system will:
- Verify module installation
- Check data consistency
- Validate access controls
- Confirm views loaded
- Verify API endpoints
- Check record integrity
- Validate foreign keys

### Step 7: Complete
On success, you'll see:
```
✅ Upgrade completed successfully!
   Upgrade ID: UPGRADE_20260613_143022
   Duration: 2.5 minutes
   Backup: /backups/elsx_20260613_143022.sql
```

---

## 📝 Manual Upgrade (Advanced)

If you need to upgrade via code:

```python
from odoo import api, http

# In your custom upgrade script:
from addons.elsx_saas.migrations import perform_upgrade

@http.route('/api/upgrade', auth='admin', methods=['POST'])
def trigger_upgrade(self):
    result = perform_upgrade(
        request.env,
        from_version='19.0.1.2.1',
        to_version='19.0.2.0.0'
    )
    return result
```

Or in Odoo shell:
```bash
$ odoo-bin shell -d FiberaFRP_DB -c /etc/odoo/odoo.conf

>>> from addons.elsx_saas.migrations import perform_upgrade
>>> result = perform_upgrade(env)
>>> print(result)
{'success': True, 'duration_minutes': 2.5, ...}
```

---

## 🔄 Rollback Procedure (If Needed)

### Automatic Rollback
If post-upgrade checks fail, the system may offer automatic rollback:

```
Click: "Rollback Upgrade"
System will restore from backup
```

### Manual Rollback

1. **Locate Backup**
   ```
   Navigate to: SaaS Admin → Settings → Backup & Recovery
   Find upgrade backup: UPGRADE_20260613_143022
   ```

2. **Restore Backup**
   ```bash
   # Using PostgreSQL
   psql FiberaFRP_DB < /backups/elsx_20260613_143022.sql

   # Or using Odoo backup
   odoo-bin -d FiberaFRP_DB --restore-file=/backups/odoo_backup.zip
   ```

3. **Verify Rollback**
   ```
   Navigate to: Apps → Verify SaaS module version
   Should show: v19.0.1.2.1
   ```

4. **Document Rollback**
   ```
   Navigate to: SaaS Admin → Upgrade Logs
   Find upgrade record, click "Log Rollback"
   ```

---

## 🆕 New Enterprise Features

After upgrade, you'll have access to:

### 1. Custom Fields
- Add tenant-specific fields without code
- Location: SaaS Admin → Settings → Custom Fields

### 2. Workflow Automation
- Automate business processes
- Location: SaaS Admin → Automation → Workflows

### 3. Scheduled Jobs
- Set up automated maintenance
- Location: SaaS Admin → Automation → Scheduled Jobs

### 4. Advanced Security
- IP whitelisting, rate limiting, SSO ready
- Location: SaaS Admin → Security → Security Policies

### 5. Multi-Tenant Reporting
- New report templates
- Location: SaaS Admin → Reports → Report Templates

---

## 📊 Upgrade Log & Tracking

All upgrades are logged in:
```
SaaS Admin → System → Upgrade Logs
```

Each log entry shows:
- Upgrade ID (UPGRADE_20260613_143022)
- From/To versions
- Pre-check results
- Migration details
- Post-check results
- Backup location
- Duration
- Success/Failure status

---

## ⚠️ Troubleshooting

### "Pre-checks failed"
**Issue**: Backup not found, active sessions, low disk space

**Solution**:
- Create backup: SaaS Admin → Backups
- Log out all users
- Free up disk space (delete old logs)
- Retry upgrade

### "Data consistency issues"
**Issue**: Invalid data found during checks

**Solution**:
- Click "View Issues" to see details
- Fix data manually or contact support
- Retry upgrade

### "Migration timeout"
**Issue**: Upgrade takes too long (> 30 minutes for large databases)

**Solution**:
- This is safe - upgrade continues in background
- Check status at: SaaS Admin → Upgrade Logs
- Contact support if not completing

### "Post-checks failed - rollback offered"
**Issue**: Something wrong after upgrade

**Solution**:
- Click "Rollback Upgrade"
- System restores backup
- Investigate issue
- Contact support before retrying

---

## 🔐 Data Safety Features

### 1. Immutable Backup
- Backup cannot be deleted once created
- Stored in secure location
- Verified before upgrade proceeds

### 2. Transaction Rollback
- All migrations run in transaction
- If any step fails, entire upgrade rolls back
- No partial upgrades

### 3. Audit Trail
- Every change logged
- Cannot be modified
- Compliance-ready

### 4. Data Validation
- Pre-upgrade: 8 validation checks
- Post-upgrade: 8 verification checks
- Data integrity verified throughout

---

## 📞 Support

**If upgrade fails:**
1. Check: SaaS Admin → Upgrade Logs → Find your upgrade
2. Click: "View Error Details"
3. Email error details to: support@elsx-erp.com

**Include in Support Request:**
- Upgrade ID
- Error message
- Database size
- Current version
- Error logs (SaaS Admin → System → Logs)

---

## ✅ Post-Upgrade Verification

After successful upgrade, verify:

1. **Check Version**
   - Navigate: Apps → Installed Modules
   - Search: "SaaS"
   - Version should be: 19.0.2.0.0

2. **Test New Features**
   - SaaS Admin → Custom Fields (Create a test field)
   - SaaS Admin → Security (Create a policy)
   - SaaS Admin → Scheduled Jobs (View defaults)

3. **Verify Existing Data**
   - SaaS Admin → Tenants (All tenants should be there)
   - SaaS Admin → Billing (Plans should be there)
   - SaaS Admin → API Tokens (Tokens should be there)

4. **Test API**
   ```bash
   curl -X GET https://your-odoo.com/api/saas/v1/health
   # Should return 200 OK with health status
   ```

5. **Check Logs**
   - SaaS Admin → Upgrade Logs → Find your upgrade
   - Status should be: "Completed Successfully"

---

## ⏱️ Typical Upgrade Timeline

| Phase | Duration | What's Happening |
|-------|----------|------------------|
| Pre-Checks | 1-2 min | Validating system is ready |
| Backup | 2-5 min | Creating full backup |
| Migration | 2-10 min | Migrating data & setting up new features |
| Post-Checks | 1-2 min | Verifying everything works |
| **Total** | **5-20 min** | Depending on database size |

**For 1GB+ databases**: Upgrade may take 20-30 minutes

---

## 🎯 Key Points to Remember

1. **Zero Downtime** - System continues running during upgrade
2. **Zero Data Loss** - Complete backup before any changes
3. **Reversible** - Full rollback capability if needed
4. **Safe by Default** - Pre-checks prevent unsafe upgrades
5. **Well-Logged** - Every step tracked with immutable logs

---

## 📚 Additional Resources

- **Complete Documentation**: See README.md
- **API Reference**: See API_DOCUMENTATION.md
- **Troubleshooting**: See this guide's Troubleshooting section
- **Support**: Email support@elsx-erp.com

---

**Ready to upgrade? Start the upgrade process and let the system handle the rest safely!** 🚀
