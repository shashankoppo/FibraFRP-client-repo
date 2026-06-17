# ELSx SaaS API Documentation

## API Base URL

```
https://your-odoo-instance/api/saas/v1
```

## Authentication

All endpoints (except `/health`) require Bearer token authentication:

```
Authorization: Bearer <api_token_key>
```

Token keys start with `elsx_` and are obtained from:
- `ELSx SaaS Admin → API & Integration → API Tokens`
- Generate one token per integration
- Tokens are immutable once created (regenerate if needed)

## Response Format

All responses are JSON with optional HTTP status codes:

### Success Response (200 OK)
```json
{
  "status": "ok",
  "data": { /* resource data */ },
  "timestamp": "2026-06-13T10:30:45"
}
```

### Error Response (4xx/5xx)
```json
{
  "error": "Error message describing what went wrong",
  "error_code": "INVALID_TOKEN",
  "timestamp": "2026-06-13T10:30:45"
}
```

## Endpoints

### 1. Health Check (Public)

Check SaaS platform availability - no authentication required.

**Request:**
```bash
GET /api/saas/v1/health
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "timestamp": "2026-06-13T10:30:45",
  "version": "v1"
}
```

**Error Handling:**
- 500 Internal Server Error: Platform issue, check server logs

---

### 2. Get Tenant Information

Retrieve basic tenant configuration and status.

**Request:**
```bash
GET /api/saas/v1/tenant/info
Authorization: Bearer elsx_xxxxx
```

**Response (200 OK):**
```json
{
  "tenant_id": 42,
  "name": "TechStartup",
  "database": "elsx_techstartup",
  "plan": "business",
  "health_status": "ok",
  "active": true,
  "max_users": 100,
  "storage_quota_gb": 100,
  "enabled_modules": {
    "crm": true,
    "accounting": true,
    "whatsapp": true,
    "attendance": true,
    "tally": false,
    "face_attendance": false
  }
}
```

**Error Handling:**
- 401 Unauthorized: Invalid or expired token
- 403 Forbidden: Token has insufficient permissions

---

### 3. Get Tenant Usage Metrics

Retrieve current usage statistics for the tenant.

**Request:**
```bash
GET /api/saas/v1/tenant/usage
Authorization: Bearer elsx_xxxxx
```

**Response (200 OK):**
```json
{
  "tenant_id": 42,
  "usage_date": "2026-06-13",
  "active_users": 25,
  "total_users": 50,
  "user_limit_percentage": 50.0,
  "used_storage_gb": 42.3,
  "storage_limit_percentage": 42.3,
  "api_requests": 12450,
  "backup_status": "success"
}
```

**Fields:**
- `active_users`: Users who logged in today
- `total_users`: Provisioned users
- `user_limit_percentage`: % of user quota used
- `used_storage_gb`: GB of storage consumed
- `storage_limit_percentage`: % of storage quota used
- `api_requests`: API calls today
- `backup_status`: `success`, `warning`, `failed`, or `unknown`

**Error Handling:**
- 401 Unauthorized: Invalid token
- 404 Not Found: Tenant not found
- 204 No Content: No usage data available yet (new tenant)

---

### 4. Get Latest Health Check

Retrieve the most recent health check results.

**Request:**
```bash
GET /api/saas/v1/tenant/health
Authorization: Bearer elsx_xxxxx
```

**Response (200 OK):**
```json
{
  "tenant_id": 42,
  "check_date": "2026-06-13T10:15:30",
  "status": "ok",
  "reachable": true,
  "response_time_ms": 45.2,
  "database_ok": true,
  "storage": "ok",
  "modules_ok": true,
  "has_alerts": false,
  "alert_message": ""
}
```

**Status Values:**
- `ok`: All systems nominal
- `warning`: Non-critical issues present
- `error`: Service degradation
- `critical`: System down or critical failure
- `unknown`: No health check data yet

**Error Handling:**
- 401 Unauthorized: Invalid token
- 404 Not Found: Tenant not found
- 204 No Content: No health check data available yet

---

### 5. Get 7-Day Performance Metrics

Retrieve historical performance data for the last 7 days.

**Request:**
```bash
GET /api/saas/v1/tenant/metrics
Authorization: Bearer elsx_xxxxx
```

**Response (200 OK):**
```json
{
  "tenant_id": 42,
  "metrics": [
    {
      "date": "2026-06-13",
      "active_users": 25,
      "storage_gb": 42.3,
      "api_requests": 12450,
      "crm_records": 342,
      "invoices": 18
    },
    {
      "date": "2026-06-12",
      "active_users": 22,
      "storage_gb": 41.8,
      "api_requests": 11230,
      "crm_records": 298,
      "invoices": 15
    }
    // ... more data
  ]
}
```

**Array Order:** Newest to oldest (descending by date)

**Error Handling:**
- 401 Unauthorized: Invalid token
- 404 Not Found: Tenant not found
- 200 OK (empty array): No metrics yet

---

### 6. Test Webhook Delivery

Send a test webhook to verify delivery configuration.

**Request:**
```bash
POST /api/saas/v1/webhook/test
Authorization: Bearer elsx_xxxxx
Content-Type: application/json

{
  "webhook_url": "https://your-tenant.com/api/webhook"
}
```

**Response (200 OK):**
```json
{
  "event_id": 156,
  "status": "success",
  "message": "Webhook test event created",
  "http_status": 200,
  "delivery_time_ms": 234.5
}
```

**Possible Statuses:**
- `success`: Webhook delivered and accepted (HTTP 2xx)
- `pending`: Webhook pending delivery (async)
- `failed`: Delivery failed after retries
- `retrying`: Delivery in progress (retry attempt)

**Request Body:**
- `webhook_url` (required): Full HTTPS URL to receive the webhook

**Error Handling:**
- 401 Unauthorized: Invalid token
- 400 Bad Request: Missing `webhook_url`
- 404 Not Found: Tenant not found
- 500 Internal Error: Failed to create webhook event

---

## Webhook Events

When webhooks are configured, the platform sends POST requests to your endpoint:

### Event Payload Format

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

### Request Headers

```
POST /your-webhook-endpoint HTTP/1.1
Host: your-tenant.com
Content-Type: application/json
Content-Length: 245
X-SaaS-Event: tenant_activated
X-SaaS-Tenant: 42
X-SaaS-Timestamp: 2026-06-13T10:30:45
```

### Webhook Events

| Event Type | Trigger | Data Included |
|-----------|---------|---------------|
| `tenant_created` | New tenant registered | tenant_name, plan, database |
| `tenant_activated` | Tenant moved to active | tenant_name, database, plan |
| `tenant_suspended` | Tenant suspended | tenant_name, database |
| `tenant_deleted` | Tenant archived | tenant_name |
| `module_installed` | Module installed | module_name, version |
| `module_failed` | Module failed to install | module_name, error_message |
| `user_created` | New user provisioned | user_email, user_name |
| `user_deleted` | User deprovisioned | user_email |
| `backup_completed` | Backup succeeded | backup_date, size_mb |
| `backup_failed` | Backup failed | backup_date, error_message |
| `health_alert` | Health check alert | status, alert_message |
| `payment_due` | Payment due | invoice_number, amount, due_date |
| `payment_failed` | Payment transaction failed | invoice_number, error |
| `storage_exceeded` | Storage quota exceeded | used_gb, limit_gb |
| `custom` | Custom event (testing) | custom_data |

### Webhook Retry Policy

- Initial delivery attempt
- Retry 1: After 5 minutes
- Retry 2: After 15 minutes
- Retry 3: After 1 hour
- Retry 4: After 6 hours
- Retry 5: After 24 hours
- Final failure after 5 failed attempts

### Webhook Response

Your endpoint should respond with HTTP 200-204 to acknowledge receipt:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "received"}
```

---

## Rate Limiting

Rate limits depend on your subscription plan:

| Plan | API Calls/Day | Concurrent | Webhook Concurrent |
|------|--------------|-----------|-------------------|
| Starter | 10,000 | 10 | 5 |
| Business | 100,000 | 100 | 25 |
| Enterprise | 1,000,000 | 1,000 | 100 |

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100000
X-RateLimit-Remaining: 99745
X-RateLimit-Reset: 1623552000
```

When limit exceeded: **429 Too Many Requests**

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_TOKEN` | 401 | Token is invalid or malformed |
| `TOKEN_EXPIRED` | 401 | Token has expired |
| `INSUFFICIENT_PERMISSIONS` | 403 | Token lacks required permissions |
| `IP_NOT_ALLOWED` | 403 | Request IP not in token whitelist |
| `TENANT_NOT_FOUND` | 404 | Tenant doesn't exist or access denied |
| `TENANT_INACTIVE` | 400 | Tenant is suspended or archived |
| `INVALID_WEBHOOK_URL` | 400 | Webhook URL is invalid or unreachable |
| `RATE_LIMIT_EXCEEDED` | 429 | API rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Internal server error |

---

## Example Integration

### Python Example

```python
import requests
import json

API_BASE = "https://your-odoo.com/api/saas/v1"
TOKEN = "elsx_your_token_key_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Get tenant info
response = requests.get(f"{API_BASE}/tenant/info", headers=headers)
if response.status_code == 200:
    tenant = response.json()
    print(f"Tenant: {tenant['name']}")
    print(f"Status: {tenant['health_status']}")
else:
    print(f"Error: {response.status_code} - {response.text}")

# Get usage metrics
response = requests.get(f"{API_BASE}/tenant/usage", headers=headers)
if response.status_code == 200:
    usage = response.json()
    print(f"Active Users: {usage['active_users']}/{usage['total_users']}")
    print(f"Storage: {usage['used_storage_gb']}GB/{usage['storage_quota_gb']}GB")
```

### JavaScript/Node.js Example

```javascript
const API_BASE = "https://your-odoo.com/api/saas/v1";
const TOKEN = "elsx_your_token_key_here";

async function getTenantInfo() {
  const response = await fetch(`${API_BASE}/tenant/info`, {
    method: "GET",
    headers: {
      "Authorization": `Bearer ${TOKEN}`,
      "Content-Type": "application/json"
    }
  });

  if (response.ok) {
    const tenant = await response.json();
    console.log(`Tenant: ${tenant.name}`);
    return tenant;
  } else {
    throw new Error(`API Error: ${response.status}`);
  }
}

async function monitorTenant() {
  const tenant = await getTenantInfo();

  const usageResponse = await fetch(`${API_BASE}/tenant/usage`, {
    headers: { "Authorization": `Bearer ${TOKEN}` }
  });

  const usage = await usageResponse.json();
  console.log(`Users: ${usage.active_users}/${usage.total_users}`);
  console.log(`Storage: ${usage.used_storage_gb}GB`);

  if (usage.user_limit_percentage > 80) {
    console.warn("User limit approaching!");
  }
}
```

### cURL Examples

```bash
# Health check
curl -X GET https://your-odoo.com/api/saas/v1/health

# Get tenant info
curl -X GET https://your-odoo.com/api/saas/v1/tenant/info \
  -H "Authorization: Bearer elsx_xxxxx"

# Get usage metrics
curl -X GET https://your-odoo.com/api/saas/v1/tenant/usage \
  -H "Authorization: Bearer elsx_xxxxx"

# Test webhook
curl -X POST https://your-odoo.com/api/saas/v1/webhook/test \
  -H "Authorization: Bearer elsx_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-tenant.com/webhook"}'
```

---

## Versioning & Deprecation

**Current Version:** v1 (stable)

All endpoints starting with `/api/saas/v1/` are guaranteed to be backward compatible within the v1 lifecycle. Breaking changes will be announced 90 days before moving to v2.

---

## Support & Issues

- **API Status**: https://status.elsx-erp.com
- **Issue Reporting**: Create support ticket with API error details
- **SDK**: Official SDKs available for Python, Node.js, PHP, Ruby
- **Documentation**: https://docs.elsx-erp.com/api

---

## Changelog

### v1.0.0 (2026-06-01)
- ✅ Health check endpoint
- ✅ Tenant info endpoint
- ✅ Usage metrics endpoint
- ✅ Health check history endpoint
- ✅ Performance metrics endpoint
- ✅ Webhook test endpoint
- ✅ Bearer token authentication
- ✅ Rate limiting by plan
- ✅ Audit logging
