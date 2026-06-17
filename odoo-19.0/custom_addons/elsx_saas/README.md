# ELSx SaaS Administration Console

**Enterprise-grade SaaS management platform** with tenant lifecycle management, API integration, billing automation, health monitoring, and support ticketing.

## Overview

The ELSx SaaS module provides a complete, production-safe SaaS management infrastructure for multi-tenant Odoo deployments. It is intentionally conservative:

- ❌ Does not create or drop PostgreSQL databases from the browser
- ❌ Does not copy credentials between tenants
- ❌ Does not modify existing production records
- ❌ Does not uninstall modules from the UI
- ✅ Generates operator deployment plans for server execution
- ✅ Manages billing, subscriptions, and revenue
- ✅ Tracks tenant health, usage, and performance
- ✅ Provides secure API access with audit logging
- ✅ Handles support tickets with SLA tracking

---

## Core Features

### 1. Tenant Registry & Lifecycle Management

Manage tenant onboarding and deployment:
- **States**: Draft → Requested → Provisioning → Active (or Suspended/Archived)
- **Preflight Checks**: Backup verification, DNS/proxy setup, capacity planning
- **Go-Live Checklist**: Database creation, module upgrades, webhook verification
- **Safety Confirmations**: Prevents premature deployment without full preparation
- **Database Naming**: Auto-generated from tenant name (e.g., `elsx_techstartup`)

**Location**: `ELSx SaaS Admin → Tenants`

#### Workflow Example
1. Create tenant record in Draft state
2. Configure admin email, domain, plan, and enabled apps
3. Verify encrypted backup and DNS/reverse proxy setup
4. Mark "Allow Provision Request" checkbox
5. Click "Request Provisioning"
6. Use generated deployment plan on server
7. Mark database created, modules upgraded
8. Click "Mark Active" once webhook is verified

---

### 2. API Token Management & Integration

Secure tenant integration via REST API:

**Features**:
- Generate unique bearer tokens per tenant
- Set expiration dates and permission levels
- IP address whitelisting
- Scope-based access (all resources, tenant-only, specific models)
- Audit logging of all API calls
- Token regeneration without downtime

**Token Permissions**:
- `Read-Only`: GET requests only
- `Read/Write`: GET, POST, PATCH allowed
- `Admin`: Full access

**Location**: `ELSx SaaS Admin → API & Integration → API Tokens`

#### REST API Endpoints

All endpoints require `Authorization: Bearer <token_key>` header.

##### Health Check
```bash
curl -X GET https://your-domain/api/saas/v1/health
```
Returns: SaaS platform health (no auth required)

##### Get Tenant Info
```bash
curl -X GET https://your-domain/api/saas/v1/tenant/info \
  -H "Authorization: Bearer elsx_xxxxx"
```

##### Get Tenant Usage Metrics
```bash
curl -X GET https://your-domain/api/saas/v1/tenant/usage \
  -H "Authorization: Bearer elsx_xxxxx"
```

##### Get Latest Health Check
```bash
curl -X GET https://your-domain/api/saas/v1/tenant/health \
  -H "Authorization: Bearer elsx_xxxxx"
```

##### Get 7-Day Performance Metrics
```bash
curl -X GET https://your-domain/api/saas/v1/tenant/metrics \
  -H "Authorization: Bearer elsx_xxxxx"
```

##### Test Webhook Delivery
```bash
curl -X POST https://your-domain/api/saas/v1/webhook/test \
  -H "Authorization: Bearer elsx_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-tenant.com/webhook"}'
```

---

### 3. Billing & Subscription Management

Complete billing automation:

**Billing Plans** (`ELSx SaaS Admin → Billing & Subscriptions → Billing Plans`):
- Pre-configured plans: Starter, Business, Enterprise, Custom
- Monthly and annual pricing with discounts
- Setup fees and per-unit costs
- Feature inclusion matrix (CRM, Accounting, WhatsApp, Attendance, etc.)
- User and storage quotas per plan
- Support tier assignment (Community, Standard, Priority, Enterprise)

**Subscriptions** (`ELSx SaaS Admin → Billing & Subscriptions → Subscriptions`):
- Automatic billing cycle tracking
- Trial period management
- Auto-renewal configuration
- Add-on management (extra users, storage, support upgrades)
- Upgrade/downgrade workflows
- Payment method tracking

**Invoicing** (`ELSx SaaS Admin → Billing & Subscriptions → Invoices`):
- Automatic invoice generation per billing cycle
- Line item detail (base fees, add-ons, adjustments, taxes)
- Payment status tracking (Draft, Sent, Partial, Paid, Overdue)
- Payment date and amount recording
- Multi-currency support

**Default Plans**:
| Plan | Monthly | Annual | Users | Storage | Support |
|------|---------|--------|-------|---------|---------|
| Starter | $29 | $290 | 10 | 5GB | Standard |
| Business | $99 | $950 | 100 | 100GB | Priority |
| Enterprise | $499 | $4,990 | 500 | 500GB | 24x7 |

---

### 4. Tenant Health Monitoring

Automated health checks and alerting:

**Location**: `ELSx SaaS Admin → Monitoring & Health → Health Checks`

**Checks Performed**:
- HTTP reachability and response time
- Database connectivity
- Filestore/storage status
- Critical module activation
- Backup status verification
- Overall health status calculation

**Health Statuses**:
- **OK**: All systems nominal
- **Warning**: Non-critical issues (e.g., slow response time)
- **Error**: Service degradation
- **Critical**: System down or critical failure

Each health check is timestamped and historized for trending analysis.

---

### 5. Usage Analytics & Metrics

Track tenant consumption and SaaS metrics:

**Location**: `ELSx SaaS Admin → Monitoring & Health → Usage Metrics`

**Tracked Metrics** (daily):
- Active users and user limit percentage
- Storage used and quota percentage
- CRM records created
- Invoices generated
- Attendance entries
- WhatsApp messages sent
- API request count and errors
- Average response time
- Database size and backup status

**Alerts**:
- Automatic warning when user limit reaches 80%
- Automatic warning when storage reaches 80%
- Usage trends and anomaly detection

---

### 6. Support Ticket Management

Professional support workflow with SLA tracking:

**Location**: `ELSx SaaS Admin → Support & Tickets → Support Tickets`

**Features**:
- Unique ticket numbering (TICKET/00001, etc.)
- Multi-level categorization (Billing, Technical, Feature Request, etc.)
- Priority levels (Critical, High, Normal, Low)
- Severity levels (Critical, High, Medium, Low)
- SLA timer by priority:
  - Critical: 1 hour
  - High: 4 hours
  - Normal: 24 hours
  - Low: 72 hours
- Ticket states: New → Assigned → In Progress → Resolved → Closed
- Internal notes (staff only) vs. customer messages
- File attachments
- First response tracking
- Resolution time tracking
- Customer satisfaction survey (Satisfied, Neutral, Unsatisfied)

**Workflow**:
1. Tenant submits issue via support channel
2. Support staff creates ticket and assigns
3. Work on resolution with internal notes
4. Mark "Waiting for Customer" if additional info needed
5. Send customer message with progress/resolution
6. Mark "Resolved" with resolution notes
7. Close ticket after verification
8. Collect satisfaction feedback

---

### 7. Webhook Events & Integrations

Event-driven integration system:

**Event Types**:
- `tenant_created` - New tenant registered
- `tenant_activated` - Tenant moved to active state
- `tenant_suspended` - Tenant suspended
- `tenant_deleted` - Tenant archived/deleted
- `module_installed` - Module successfully installed
- `module_failed` - Module installation failed
- `user_created` - New user provisioned
- `user_deleted` - User deprovisioned
- `backup_completed` - Scheduled backup succeeded
- `backup_failed` - Backup failed
- `health_alert` - Health check alert triggered
- `payment_due` - Subscription payment due
- `payment_failed` - Payment failed
- `storage_exceeded` - Storage quota exceeded
- `custom` - Custom event (for testing)

**Webhook Payload**:
```json
{
  "event_type": "tenant_activated",
  "tenant_id": 42,
  "timestamp": "2026-06-13T10:30:45",
  "data": {
    "tenant_name": "TechStartup",
    "database": "elsx_techstartup",
    "plan": "business"
  }
}
```

**Headers**:
- `X-SaaS-Event`: Event type
- `X-SaaS-Tenant`: Tenant ID
- `X-SaaS-Timestamp`: ISO 8601 timestamp

**Delivery**:
- Automatic retry up to 5 times
- Status tracking: Pending → Success/Failed
- HTTP status code and response body logging
- Manual delivery test via `/api/saas/v1/webhook/test`

---

## Recommended Deployment Model

### Multi-Database, Single Odoo Instance
```
Production Odoo Instance
├── FiberaFRP_DB (main SaaS management database)
├── elsx_techstartup_db (Tenant 1)
├── elsx_globalcorp_db (Tenant 2)
└── elsx_luxurybrands_db (Tenant 3)
```

**Benefits**:
- Tenant data isolation
- Per-tenant backup and restore
- Per-tenant module upgrades
- Per-tenant customization

**SaaS Console**:
- Runs in `FiberaFRP_DB` (production master)
- Manages all tenant lifecycle
- Tracks billing, health, support
- Generates deployment commands

---

## Server-Side Operations

All production database operations use safe shell scripts, **never** direct UI buttons.

### Production Backup
```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_backup.sh FiberaFRP_DB
bash deploy/safe_production_backup.sh elsx_techstartup_db
```

### Production Upgrade
```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE

# Upgrade elsx_techstartup for CRM, Accounting, WhatsApp
EXTRA_UPGRADE_MODULES=crm,account,elsx_whatsapp_marketing bash deploy/safe_production_update.sh elsx_techstartup_db
```

### Health Check (Cron/Manual)
```bash
# Run from Odoo shell
from odoo import api, models
env = api.Environment(cr, uid, {})
for tenant in env['elsx.saas.tenant'].search([('state', '=', 'active')]):
    tenant._run_health_check()
```

---

## Access Control

**User Groups**:
- `System Administrator` (base.group_system) - Full access
- `ELSx SaaS Administrator` (elsx_saas.group_elsx_saas_admin) - SaaS console access
- `Regular User` (base.group_user) - View-only; can create support tickets

**Model Permissions**:
| Model | Admin | System | User |
|-------|-------|--------|------|
| Tenant | RWC | RWC | R |
| Module Request | RWC | RWC | R |
| API Token | RWC | R | — |
| Health Check | RWC | R | — |
| Usage Metrics | RWC | R | — |
| Support Ticket | RWC | R | RWC |
| Billing Plan | RWC | RWC | R |
| Invoice | RWC | R | — |
| Subscription | RWC | R | — |

---

## Admin Workflow

### Tenant Onboarding
1. **Prepare Infrastructure**
   - Allocate server resources
   - Plan database sizing
   - Configure reverse proxy
   - Set up DNS CNAME record

2. **Create Tenant Record**
   - Navigate to `ELSx SaaS Admin → Tenants`
   - Click "Create"
   - Enter tenant name (becomes default subdomain)
   - Set admin email, legal name, custom domain
   - Choose plan (Starter/Business/Enterprise/Custom)
   - Select enabled modules/features

3. **Pre-Flight Checks**
   - ✓ Encrypted backup created and verified
   - ✓ DNS and reverse proxy configured
   - ✓ Capacity check done
   - ✓ Enable "Allow Provision Request" checkbox

4. **Request Provisioning**
   - Click "Request Provisioning" button
   - Review generated deployment plan
   - State changes to "Provision Requested"

5. **Deploy on Server**
   ```bash
   # Copy and run deployment plan commands
   # Example output includes:
   read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
   export BACKUP_PASSPHRASE
   EXTRA_UPGRADE_MODULES=elsx_client_restrictions,contacts,crm,sale,account \
     bash deploy/safe_production_update.sh elsx_techstartup_db
   ```

6. **Mark Deployment Complete**
   - Mark "Database Created" checkbox
   - Mark "Modules Upgraded" checkbox
   - Verify webhook access
   - Mark "Webhook Checked" checkbox
   - Click "Mark Active" button

7. **Go Live**
   - Tenant state: "Active"
   - Generate API token for tenant integration
   - Share login credentials with tenant admin
   - Schedule training/onboarding

### Managing Active Tenants
- **Monitor Health**: View latest health check, usage metrics
- **Support Issues**: Create and track support tickets
- **Billing**: Generate and send invoices, track payments
- **Scaling**: Upgrade plan, add users, increase storage
- **API Integration**: Generate tokens, test webhook delivery
- **Module Updates**: Request third-party module additions
- **Suspend**: Temporarily disable access (preserves data)
- **Archive**: Permanently mark as inactive (preserves data)

---

## Key Business Metrics

**Revenue Tracking**:
- Monthly Recurring Revenue (MRR) per tenant
- Annual Recurring Revenue (ARR) per plan
- Setup fees and one-time costs
- Churn rate and customer lifetime value

**Tenant Health**:
- Uptime percentage
- Average response time
- Error rate
- Module compatibility

**Support Metrics**:
- Average first response time
- SLA breach rate
- Customer satisfaction score
- Ticket resolution time

---

## Security Considerations

### API Token Security
- Tokens stored hashed (SHA-256)
- Unique per tenant and use case
- Expiration tracking (default 90 days)
- IP address whitelisting supported
- Scope-based access control
- Audit logging of all API calls

### Tenant Isolation
- Separate PostgreSQL database per tenant
- No cross-tenant data sharing from SaaS console
- Credentials not exposed in UI
- Deployment script encryption support

### Compliance & Audit
- Immutable audit logs (no deletion allowed)
- API call tracking with timestamps and response codes
- Deployment plan approval workflow
- Backup verification before provisioning

---

## Customization & Extension

### Adding Custom Billing Add-ons
```python
# Create new add-on
addon = env['elsx.saas.addon'].create({
    'name': 'Custom API Rate Boost',
    'monthly_price': 49,
})
```

### Adding Custom Health Checks
```python
# In tenant model or service
def _custom_health_check(self):
    result = {
        'overall_status': 'ok',
        'custom_metric': value,
    }
    self.env['elsx.saas.health.check'].record_health_check(
        self.id, result
    )
```

### Triggering Custom Webhook Events
```python
# From any model
env['elsx.saas.webhook.event'].trigger_webhook(
    tenant_id,
    'custom',
    {'your': 'data', 'here': True}
)
```

---

## Troubleshooting

### API Token Not Working
- Verify token is active (not deactivated)
- Check expiration date
- Verify IP address in whitelist (if configured)
- Review API audit log for failed requests
- Regenerate token if compromised

### Webhook Delivery Failing
- Check webhook URL is accessible
- Verify HTTP status code in event log
- Test with `/api/saas/v1/webhook/test` endpoint
- Increase delivery retry limit if needed
- Check firewall and network rules

### Health Check Alert
- Review latest health check record
- Check database connectivity
- Verify filestore permissions
- Review error details in check_result field
- Restart Docker containers if needed

### Billing Discrepancies
- Verify plan pricing and dates
- Check for applied discounts
- Review invoice line items
- Audit subscription changes
- Reconcile with payment records

---

## Version History

### v19.0.2.0.0 (Enterprise Edition)
- ✅ API token management and audit logging
- ✅ Billing plans, invoicing, subscriptions
- ✅ Support ticket system with SLA tracking
- ✅ Health monitoring and usage analytics
- ✅ Webhook events and integrations
- ✅ REST API v1 with 5 core endpoints

### v19.0.1.2.1 (Initial Release)
- ✅ Tenant registry and lifecycle
- ✅ Module request workflow
- ✅ Deployment plan generation
- ✅ Safety checklist and confirmations

---

## Support & Contact

- **Documentation**: https://elsx-erp.com/docs/saas
- **Support Email**: support@elsx-erp.com
- **Community Forum**: https://forum.elsx-erp.com
- **GitHub Issues**: https://github.com/elsx-evolution/odoo-saas

---

## License

© 2026 ELSX Evolution Engine. All rights reserved.

This module contains proprietary code and configurations. Unauthorized copying or distribution is prohibited.
