# ELSx SaaS Quick Start Guide

## Installation Quick Start

### 1. Copy Module to Addons
```bash
cd /path/to/odoo-19.0/custom_addons
ls -la | grep elsx_saas  # Should show the directory
```

### 2. Install Module in Odoo UI
- Open `Apps`
- Search for "SaaS"
- Find "ELSX ERP SaaS Master"
- Click "Install"

### 3. Verify Installation
- Check `ELSx SaaS Admin` menu appears
- Access `Tenants` view
- Access `API Tokens` view

---

## Quick Workflows

### Create Your First Tenant

1. **Navigate**: `ELSx SaaS Admin → Tenants`
2. **Click**: Create
3. **Fill Form**:
   - Name: `My First Tenant` (becomes subdomain)
   - Admin Email: `admin@mytenant.com`
   - Plan: `Starter` (default)
   - Enabled Modules: Check desired features
4. **Safety Checklist**:
   - ✓ Backup Verified
   - ✓ Allow Provision Request
5. **Click**: `Request Provisioning`
6. **Copy**: Deployment plan from `Deployment Plan` tab
7. **Run** on server: Paste commands into terminal
8. **Mark Complete**:
   - ✓ Database Created
   - ✓ Modules Upgraded
   - ✓ Webhook Checked
9. **Click**: `Mark Active`

### Generate API Token

1. **Navigate**: `ELSx SaaS Admin → API & Integration → API Tokens`
2. **Click**: Create
3. **Fill**:
   - Description: `Mobile App Integration`
   - Permissions: `Read-Only` (or appropriate level)
   - Scope: `Tenant Only`
   - Expires: Set expiry date
4. **Save**
5. **View**: Token key displays (save securely)

### Track Tenant Health

1. **Navigate**: `ELSx SaaS Admin → Monitoring & Health → Health Checks`
2. **View**: Latest checks for each tenant
3. **Click**: Record to see details
4. **Inspect**: Status, response time, alerts

### Create Support Ticket

1. **Navigate**: `ELSx SaaS Admin → Support & Tickets → Support Tickets`
2. **Click**: Create
3. **Fill**:
   - Subject: Issue description
   - Category: Choose type
   - Priority: Set level
   - Description: Detailed info
4. **Assign**: To support staff member
5. **Workflow**: Assigned → In Progress → Resolved → Closed

### Set Billing Plans

1. **Navigate**: `ELSx SaaS Admin → Billing & Subscriptions → Billing Plans`
2. **View**: Pre-configured (Starter, Business, Enterprise)
3. **Edit**: Customize pricing, features, limits
4. **Create**: New plan for custom arrangements

---

## API Usage Examples

### Get Tenant Info

```bash
curl -X GET https://your-odoo.com/api/saas/v1/tenant/info \
  -H "Authorization: Bearer elsx_your_token"
```

**Response:**
```json
{
  "tenant_id": 42,
  "name": "My First Tenant",
  "plan": "starter",
  "health_status": "ok",
  "active": true
}
```

### Monitor Usage

```bash
curl -X GET https://your-odoo.com/api/saas/v1/tenant/usage \
  -H "Authorization: Bearer elsx_your_token"
```

### Check Health Status

```bash
curl -X GET https://your-odoo.com/api/saas/v1/tenant/health \
  -H "Authorization: Bearer elsx_your_token"
```

### Get 7-Day Metrics

```bash
curl -X GET https://your-odoo.com/api/saas/v1/tenant/metrics \
  -H "Authorization: Bearer elsx_your_token"
```

### Test Webhook

```bash
curl -X POST https://your-odoo.com/api/saas/v1/webhook/test \
  -H "Authorization: Bearer elsx_your_token" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-server.com/webhook"}'
```

---

## Key Concepts

### Tenant States
- **Draft**: New, not yet deployed
- **Requested**: Awaiting provisioning
- **Provisioning**: Being set up
- **Active**: Running and operational
- **Suspended**: Temporarily disabled
- **Archived**: Permanently inactive

### Health Status
- **OK**: Healthy, all systems normal
- **Warning**: Minor issues detected
- **Error**: Service degradation
- **Critical**: System down

### SLA Timers (by ticket priority)
- **Critical** (🔴): 1 hour response target
- **High** (🟠): 4 hours response target
- **Normal** (🟡): 24 hours response target
- **Low** (🟢): 72 hours response target

### Billing Plans Included
- **Starter**: $29/mo - 10 users, 5GB, CRM+Accounting
- **Business**: $99/mo - 100 users, 100GB, +WhatsApp+Attendance
- **Enterprise**: $499/mo - 500 users, 500GB, +Tally+Face

---

## Common Issues & Solutions

### API Token Not Working
**Error**: `Invalid or inactive API token`
- **Solution**:
  1. Verify token is active (not deactivated)
  2. Check expiration date hasn't passed
  3. Confirm token belongs to your tenant
  4. Try regenerating new token

### Health Check Fails
**Error**: `Database Reachable: False`
- **Solution**:
  1. Check database is running
  2. Verify network connectivity
  3. Check firewall rules
  4. Restart Odoo container if needed

### Webhook Not Delivering
**Error**: `Delivery Failed`
- **Solution**:
  1. Verify webhook URL is accessible
  2. Check HTTP endpoint is responding
  3. Review firewall/security rules
  4. Test with `/api/saas/v1/webhook/test` endpoint

### Tenant Provisioning Fails
**Error**: `Backup not verified`
- **Solution**:
  1. Create encrypted backup first
  2. Mark "Backup Verified" checkbox
  3. Retry provisioning request

---

## Performance Tuning

### For Large Deployments
1. **Enable DB Indexing**: Health checks create daily records
2. **Archive Old Tickets**: Move resolved tickets monthly
3. **Prune Audit Logs**: Keep last 90 days of API logs
4. **Optimize Queries**: Use search_count for large datasets

### Recommended Cron Jobs
```python
# Daily health checks (best at 2 AM)
for tenant in env['elsx.saas.tenant'].search([('state', '=', 'active')]):
    tenant._run_health_check()

# Weekly usage summary (Sundays 3 AM)
env['elsx.saas.tenant.usage']._generate_summary()

# Monthly billing (1st of month at 1 AM)
env['elsx.saas.billing.cycle']._generate_monthly_invoices()
```

---

## File Locations

| Purpose | Location |
|---------|----------|
| Module Directory | `/custom_addons/elsx_saas/` |
| Models | `/models/*.py` |
| Views | `/views/*.xml` |
| API Endpoints | `/controllers/saas_api.py` |
| Tests | `/tests/test_saas_models.py` |
| Documentation | `README.md`, `API_DOCUMENTATION.md` |
| CSS Styling | `/static/src/css/saas_admin.css` |

---

## Getting Help

### Documentation
- **User Guide**: See `README.md` (complete guide)
- **API Reference**: See `API_DOCUMENTATION.md`
- **Dev Guide**: See `DEVELOPMENT_SUMMARY.md`

### Support
- Create support ticket in `ELSx SaaS Admin → Support Tickets`
- Email: support@elsx-erp.com
- Forum: https://forum.elsx-erp.com

### Reporting Bugs
- Include: Module version, steps to reproduce, error logs
- Create ticket with category "technical"
- Attach screenshots if applicable

---

## Admin Checklist

- [ ] Module installed and menu visible
- [ ] Created first API token
- [ ] Configured billing plans (or verified defaults)
- [ ] Created demo/test tenant
- [ ] Ran health check (verify it passes)
- [ ] Reviewed usage metrics view
- [ ] Tested API endpoints with curl
- [ ] Created test support ticket
- [ ] Reviewed audit logs
- [ ] Set backup schedule
- [ ] Configured webhook URL (if needed)
- [ ] Trained support staff on ticketing
- [ ] Documented custom workflows

---

**Ready to use! Questions? Check docs or create support ticket.**
