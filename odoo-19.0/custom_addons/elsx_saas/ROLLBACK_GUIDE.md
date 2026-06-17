# SaaS Module Rollback Guide

**Purpose**: Safe procedure to revert from v2.0.0 back to v1.2.1
**Risk Level**: VERY LOW - Pre-created backup ensures safe restoration
**Recovery Time**: 5-15 minutes

---

## ⚡ Quick Rollback (Recommended)

### Option 1: Automatic Rollback (Easiest)

If the upgrade just failed and you're still seeing the rollback offer:

1. **Click Rollback Button**
   ```
   SaaS Admin → Upgrade Logs → Find failed upgrade
   Click: "Rollback Upgrade"
   ```

2. **Confirm**
   ```
   Confirm: "Yes, restore backup"
   ```

3. **System Automatically**
   - Stops the current version
   - Restores previous version
   - Verifies restoration
   - Confirms data integrity

4. **Verify Success**
   ```
   Check: Apps → SaaS Module Version
   Should show: 19.0.1.2.1
   ```

---

## 🔧 Manual Rollback Procedure

### Step 1: Identify Backup

Navigate to upgrade logs:
```
SaaS Admin → System → Upgrade Logs
```

Find your failed upgrade (status = "Failed" or "Rolled Back"):
```
Example:
Upgrade ID: UPGRADE_20260613_143022
Status: Failed
Backup: /backups/FiberaFRP_DB_upgrade_20260613_143022.sql
Can Rollback: Yes ✓
```

### Step 2: Prepare System

**Stop Odoo Service**
```bash
# On Linux
sudo systemctl stop odoo

# On Windows (as Administrator)
net stop Odoo
```

**Verify Stopped**
```bash
# Test connection (should fail)
psql -U odoo -d FiberaFRP_DB -c "SELECT 1"
# Should return connection refused
```

### Step 3: Restore from Backup

**Option A: PostgreSQL Backup (sql file)**
```bash
# Restore the SQL backup
psql -U odoo -d FiberaFRP_DB < /backups/FiberaFRP_DB_upgrade_20260613_143022.sql

# Verify restoration
psql -U odoo -d FiberaFRP_DB -c "\dt" | grep elsx_saas
# Should show all SaaS tables
```

**Option B: Odoo Backup File (.zip)**
```bash
# Using Odoo command line
odoo-bin \
  -d FiberaFRP_DB \
  --restore-file=/backups/FiberaFRP_DB_20260613_143022.zip \
  --restore-databases=True

# Verify
odoo-bin -d FiberaFRP_DB -c /etc/odoo/odoo.conf --shell
# Type: exit
```

**Option C: Manual Database Reset** (If backups unavailable)
```bash
# Drop current database
psql -U postgres -c "DROP DATABASE FiberaFRP_DB"

# Restore empty database
psql -U postgres -c "CREATE DATABASE FiberaFRP_DB OWNER odoo"

# Restore backup
psql -U odoo -d FiberaFRP_DB < /backups/FiberaFRP_DB_upgrade_20260613_143022.sql
```

### Step 4: Start Odoo Service

**Start Odoo**
```bash
# On Linux
sudo systemctl start odoo

# On Windows
net start Odoo
```

**Verify Started**
```bash
# Check service is running
ps aux | grep odoo

# Test connection
curl http://localhost:8069
# Should return HTML response
```

### Step 5: Verify Rollback Success

**Check in Web UI**
1. Open http://localhost:8069
2. Navigate: Apps → Search "SaaS"
3. Verify version: Should be **19.0.1.2.1**

**Check Database**
```bash
# Connect to database
psql -U odoo -d FiberaFRP_DB

# Check SaaS tables exist
\dt elsx_saas*

# Should show old SaaS tables (pre-v2.0.0)
```

**Verify Data**
```
SaaS Admin → Tenants
- All tenants should be there
- Data should be intact
- No missing records
```

---

## ⚠️ Rollback Issues & Solutions

### Issue 1: "Backup file not found"

**Error Message:**
```
Error: Backup location /backups/... does not exist
```

**Solution:**
1. Find backup in alternate location:
   ```bash
   find / -name "*FiberaFRP*" -type f 2>/dev/null | grep -E "\.(sql|zip|bak)$"
   ```

2. If found, use that path in restore command

3. If not found:
   - Check if automatic backup ran: `ls -lah /tmp/odoo_backups/`
   - Contact support with upgrade ID

### Issue 2: "Permission denied" during restore

**Error Message:**
```
psql: could not connect to server
Permission denied
```

**Solution:**
```bash
# Run with correct user/permissions
sudo -u postgres psql -d FiberaFRP_DB < /backups/...

# Or as root then fix permissions
sudo psql -U postgres < /backups/...
```

### Issue 3: "Database locked"

**Error Message:**
```
FATAL: database is locked
```

**Solution:**
```bash
# Kill active connections
sudo -u postgres psql -d FiberaFRP_DB -c \
  "SELECT pg_terminate_backend(pg_stat_activity.pid) \
   FROM pg_stat_activity \
   WHERE datname = 'FiberaFRP_DB'"

# Retry restore
psql -U odoo -d FiberaFRP_DB < /backups/...
```

### Issue 4: "Module not found" after rollback

**Error Message:**
```
Module 'elsx_saas' installed but files missing
```

**Solution:**
1. Check module location:
   ```bash
   ls -la /path/to/addons/elsx_saas/
   ```

2. If missing, restore from source control:
   ```bash
   git checkout v1.2.1 -- odoo-19.0/custom_addons/elsx_saas/
   ```

3. Restart Odoo:
   ```bash
   systemctl restart odoo
   ```

### Issue 5: "Data integrity errors" after rollback

**Error Message:**
```
Foreign key constraint violation
Orphaned records found
```

**Solution:**
1. Run repair script:
   ```bash
   odoo-bin -d FiberaFRP_DB -c /etc/odoo/odoo.conf \
     --repair-db --stop-after-init
   ```

2. Verify data:
   ```
   SaaS Admin → Settings → Data Validation
   Run checks and fix any issues
   ```

3. Contact support if issues persist

---

## 🔍 Verification Checklist

After rollback, verify:

- [ ] Odoo service is running
- [ ] Web interface accessible (http://localhost:8069)
- [ ] Logged in successfully
- [ ] SaaS module version is 19.0.1.2.1
- [ ] All tenants present and data intact
- [ ] API tokens working
- [ ] Billing records present
- [ ] Support tickets accessible
- [ ] No error logs in Odoo logs
- [ ] Database size reasonable (not bloated)

---

## 📋 Pre-Rollback Checklist

Before rolling back, ensure:

- [ ] Documented what caused the failure
- [ ] Saved upgrade logs and error details
- [ ] Backed up current v2.0.0 database (in case needed for forensics)
- [ ] Notified users that system will be temporarily unavailable
- [ ] Scheduled rollback during low-traffic period
- [ ] Have backup of v1.2.1 available

---

## 📊 Rollback Documentation

After rollback, document:

1. **When**: Date and time of rollback
2. **Why**: Reason for rollback (e.g., "Post-check failed: API endpoints not responding")
3. **Duration**: How long rollback took
4. **Who**: Who approved and performed rollback
5. **Result**: Success/Failure
6. **Next Steps**: Plan for retrying upgrade

**Location to Document:**
```
SaaS Admin → Upgrade Logs → Find upgrade record
Click: "Document Rollback"
Enter: Reason and outcome
```

---

## 🔄 Retry Upgrade

After successful rollback:

### Option 1: Immediate Retry
1. Address issues that caused failure
2. Re-run pre-upgrade checks
3. Follow upgrade procedure again

### Option 2: Upgrade in Test Environment
1. Create test copy of production database
2. Upgrade test environment first
3. Verify all features work
4. Then upgrade production

### Option 3: Contact Support
1. Provide upgrade logs
2. Include error details
3. Report rollback outcome
4. Get assistance before retrying

---

## 🆘 Emergency Rollback

If system is completely broken and normal rollback doesn't work:

### Worst-Case Recovery

```bash
# 1. Stop everything
systemctl stop odoo nginx postgresql

# 2. Check backups
ls -lah /backups/
ls -lah /tmp/odoo_backups/

# 3. Restore from most recent backup
pg_restore -U postgres -d FiberaFRP_DB \
  /backups/FiberaFRP_DB_YYYY-MM-DD_HHMMSS.sql

# 4. Start PostgreSQL
systemctl start postgresql

# 5. Start Odoo
systemctl start odoo

# 6. Verify
curl http://localhost:8069/web/login
```

### If No Backup Available

This is critical - immediately:
1. Stop all Odoo processes
2. Contact support IMMEDIATELY
3. Do not attempt manual repairs
4. Request emergency recovery assistance

---

## 📞 Support for Rollback Issues

**If rollback fails:**

1. **Gather Information**
   ```bash
   # Collect logs and diagnostics
   odoo-bin -d FiberaFRP_DB -c /etc/odoo/odoo.conf --shell \
     < diagnostic_script.py > diagnostic_output.txt
   ```

2. **Email Support with**
   - Upgrade ID that was rolled back
   - Rollback errors and logs
   - `diagnostic_output.txt`
   - Current database version check:
     ```bash
     psql -U odoo -d FiberaFRP_DB -c \
       "SELECT * FROM ir_module_module WHERE name='elsx_saas'"
     ```

3. **Support Contacts**
   - Email: support@elsx-erp.com
   - Phone: +1-XXX-XXX-XXXX (during business hours)
   - Urgent: Create high-priority ticket

---

## ✅ Success Criteria

Rollback is successful when:

1. ✅ Odoo service running and accessible
2. ✅ All SaaS tenants visible and data intact
3. ✅ Version shows 19.0.1.2.1
4. ✅ No error logs in system
5. ✅ API endpoints responding
6. ✅ Users can log in normally
7. ✅ Billing/support features working
8. ✅ Database integrity verified

---

## 📚 Related Guides

- **Upgrade Guide**: UPGRADE_GUIDE.md
- **Data Safety**: This guide emphasizes data safety
- **API Reference**: API_DOCUMENTATION.md
- **Full Documentation**: README.md

---

**Remember: Data is always backed up before any operation. Rollback is a safe procedure designed to restore your system to a known-good state.** 🛡️

---

**Questions about rollback? Check the Troubleshooting section or contact support immediately.**
