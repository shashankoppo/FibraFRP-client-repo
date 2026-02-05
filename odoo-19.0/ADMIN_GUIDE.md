# ELSX CRM & WhatsApp Marketing - Administrator Setup Guide

## Initial System Setup

### Step 1: Install the Client Restrictions Module

This module hides the Apps menu from regular users and restricts module installations.

```bash
# Restart the server and install the module
cd "c:\Users\Shashank patel\Desktop\odoo-19.0\odoo-19.0"
.\venv19\Scripts\python odoo-bin -c odoo.conf -d elsx_dev -i elsx_client_restrictions -u elsx_whatsapp_marketing
```

### Step 2: Verify Installed Modules

The system should only have these modules active:
- **Base** - Core Odoo functionality
- **Web** - Web interface
- **CRM** - Customer Relationship Management
- **Contacts** - Contact management
- **Mail** - Email and messaging
- **Discuss** - Internal chat
- **WhatsApp Marketing** - WhatsApp campaigns and messaging
- **Client Restrictions** - Hides Apps menu

### Step 3: Create User Accounts

1. **Navigate to Settings > Users & Companies > Users**
2. **Click Create**
3. **Fill in user details:**
   - Name
   - Email (used as login)
   - Password
4. **Access Rights:**
   - **Sales**: Sales User or Sales Manager
   - **WhatsApp Marketing**: User or Manager
   - **Discuss**: Check to enable chat
5. **DO NOT** give "Administration / Settings" access to regular users
6. **Click Save**

### Step 4: Configure WhatsApp Business API

**Get API Credentials from Meta:**

1. Go to [Meta Business Suite](https://business.facebook.com/)
2. Navigate to **WhatsApp Manager**
3. Select your WhatsApp Business Account
4. Go to **API Setup**
5. Note down:
   - Phone Number ID
   - Business Account ID
   - Access Token (Permanent token recommended)

**Configure in ELSX:**

1. Login as admin
2. Navigate to **WhatsApp > Configuration > Accounts**
3. Click **Create**
4. Enter all API credentials
5. Click **Test Connection**
6. Click **Sync Templates** to import approved templates

### Step 5: Set Up Webhook (Optional but Recommended)

This allows you to receive incoming WhatsApp messages.

1. In Meta Business Suite > WhatsApp > Configuration
2. Set Webhook URL: `https://your-domain.com/whatsapp/webhook/1`
   (Replace with your actual domain and account ID)
3. Set Verify Token: (same as in WhatsApp Account configuration)
4. Subscribe to: `messages`, `message_status`

### Step 6: Uninstall Unnecessary Modules (Optional)

If you want to completely remove unused modules:

```bash
# Login to database
psql -U odoo -d elsx_dev

# Uninstall modules (example)
UPDATE ir_module_module SET state='uninstalled' WHERE name IN (
    'sale', 'purchase', 'stock', 'mrp', 'website', 'ecommerce'
);
```

**Note:** Be careful with this step. Only uninstall if you're sure you don't need the functionality.

---

## User Management Best Practices

### Access Levels

**Sales User:**
- Can view and edit their own leads/opportunities
- Can send WhatsApp messages
- Can view contacts
- Cannot access settings or install apps

**Sales Manager:**
- Can view all leads/opportunities
- Can create campaigns
- Can manage team members' leads
- Cannot access technical settings

**Administrator:**
- Full access to everything
- Can install/uninstall modules
- Can configure system settings
- **Should be limited to 1-2 trusted people**

### Creating a Sales User

1. Settings > Users > Create
2. Name: John Doe
3. Email: john@company.com
4. Access Rights:
   - Sales: Sales User ✓
   - WhatsApp Marketing: User ✓
   - Discuss: ✓
5. Save

### Creating a Sales Manager

1. Settings > Users > Create
2. Name: Jane Manager
3. Email: jane@company.com
4. Access Rights:
   - Sales: Sales Manager ✓
   - WhatsApp Marketing: Manager ✓
   - Discuss: ✓
5. Save

---

## System Maintenance

### Daily Tasks
- Monitor WhatsApp message delivery rates
- Check for failed messages
- Review new leads

### Weekly Tasks
- Review campaign performance
- Clean up duplicate contacts
- Archive old conversations

### Monthly Tasks
- Database backup
- Review user access rights
- Update WhatsApp templates if needed
- Check system performance

---

## Troubleshooting

### Users Can Still See Apps Menu

**Solution:**
1. Ensure `elsx_client_restrictions` module is installed
2. Restart the server
3. Clear browser cache
4. Verify user doesn't have "Administration / Settings" access

### WhatsApp Messages Failing

**Check:**
1. Access token is valid (tokens can expire)
2. Phone numbers are in correct format (+country code)
3. Meta account is active and in good standing
4. Message templates are approved

### Performance Issues

**Solutions:**
1. Increase `limit_memory_hard` in odoo.conf
2. Add more database connections (`db_maxconn`)
3. Enable caching
4. Archive old records

---

## Security Recommendations

1. **Use Strong Passwords:**
   - Minimum 12 characters
   - Mix of letters, numbers, symbols
   - Change every 90 days

2. **Enable Two-Factor Authentication:**
   - Settings > Users > Enable 2FA for admin accounts

3. **Regular Backups:**
   - Daily automated backups
   - Store backups offsite
   - Test restore procedures monthly

4. **Access Control:**
   - Only give admin access to trusted personnel
   - Review user access quarterly
   - Disable inactive user accounts

5. **API Security:**
   - Keep access tokens secure
   - Use permanent tokens (not temporary)
   - Rotate tokens every 6 months
   - Never share tokens via email or chat

---

## Support and Updates

### Getting Help
- User Manual: `USER_MANUAL.md`
- Technical Issues: Contact system administrator
- WhatsApp API Issues: Meta Business Support

### System Updates
- Check for Odoo security updates monthly
- Test updates in staging environment first
- Schedule updates during low-traffic periods
- Always backup before updating

---

**Document Version:** 1.0  
**Last Updated:** January 31, 2026  
**For:** System Administrators Only
