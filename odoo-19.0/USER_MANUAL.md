# ELSX CRM & WhatsApp Marketing - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [CRM Module](#crm-module)
3. [WhatsApp Marketing](#whatsapp-marketing)
4. [Bulk Messaging](#bulk-messaging)
5. [Contact Management](#contact-management)
6. [Discuss (Chat)](#discuss-chat)
7. [Best Practices](#best-practices)

---

## Getting Started

### Logging In
1. Open your web browser and navigate to: `http://localhost:8069` (or your server URL)
2. Enter your username and password
3. Click **Log In**

### Dashboard Overview
After logging in, you'll see the main dashboard with the following menus:
- **CRM** - Manage leads and opportunities
- **WhatsApp** - Send messages and campaigns
- **Contacts** - Manage customer information
- **Discuss** - Internal team communication

---

## CRM Module

### Understanding CRM
The CRM (Customer Relationship Management) module helps you track and manage your sales pipeline from initial contact to closing deals.

### Creating a New Lead/Opportunity

1. **Navigate to CRM**
   - Click on **CRM** in the top menu
   - Click **Create** button (top-left)

2. **Fill in Lead Information**
   - **Opportunity Name**: Enter a descriptive name (e.g., "ABC Company - Website Design")
   - **Customer**: Select existing contact or create new
   - **Email**: Customer's email address
   - **Phone**: Customer's phone number
   - **Expected Revenue**: Estimated deal value
   - **Probability**: Likelihood of closing (0-100%)
   - **Tags**: Add relevant tags for categorization

3. **Assign and Track**
   - **Salesperson**: Assign to a team member
   - **Sales Team**: Select the responsible team
   - **Next Activity**: Schedule follow-up calls or meetings

4. **Click Save**

### Managing the Sales Pipeline

**Pipeline Stages:**
1. **New** - Fresh leads
2. **Qualified** - Verified potential customers
3. **Proposition** - Proposal sent
4. **Won** - Deal closed successfully
5. **Lost** - Deal not converted

**Moving Opportunities:**
- Drag and drop opportunities between stages in Kanban view
- Or click on an opportunity and change the **Stage** field

### Marking an Opportunity as Won

1. Open the opportunity
2. Click **Mark Won** button at the top
3. **Automatic WhatsApp Notification**: The system will automatically send a congratulatory WhatsApp message to the customer if they have a phone number

### Activities and Follow-ups

1. **Schedule Activity**
   - Click **Schedule Activity** button
   - Choose activity type (Call, Meeting, Email, etc.)
   - Set date and time
   - Add notes

2. **Log Activities**
   - Click **Log Note** to record interactions
   - Add details about conversations or meetings

---

## WhatsApp Marketing

### Setting Up WhatsApp Account

**Prerequisites:**
- WhatsApp Business API account from Meta
- Phone Number ID
- Access Token
- Business Account ID

**Configuration Steps:**

1. **Navigate to WhatsApp > Configuration > Accounts**
2. **Click Create**
3. **Fill in Account Details:**
   - **Account Name**: Give it a descriptive name (e.g., "Main Business Line")
   - **Phone Number**: Your WhatsApp Business number with country code (e.g., +919876543210)
   - **Phone Number ID**: From Meta Business Suite
   - **Business Account ID**: From Meta Business Suite
   - **Access Token**: Your API access token (keep this secure)
   - **API Version**: v18.0 (default)
   - **Webhook Verify Token**: Create a random secure string

4. **Enable AI Features (Optional)**
   - **AI Automation Enabled**: Check this box
   - **AI Model**: Select GPT-4o or Claude 3.5
   - **AI Business Context**: Describe your business (e.g., "We are a digital marketing agency specializing in social media management and SEO services. We offer 24/7 support and free consultations.")

5. **Click Save**

6. **Test Connection**
   - Click **Test Connection** button
   - Wait for success notification

7. **Sync Templates**
   - Click **Sync Templates** button
   - This will import all approved templates from Meta

### Sending Individual Messages

1. **Navigate to WhatsApp > Messages**
2. **Click Create**
3. **Fill in Message Details:**
   - **WhatsApp Account**: Select your configured account
   - **Contact**: Choose recipient from contacts
   - **Phone Number**: Auto-filled from contact
   - **Message Type**: Select "Text"
   - **Message Body**: Type your message
   
4. **Click Save and Send**

### Creating Message Templates

**Note:** Templates must be approved by Meta before use.

1. **Navigate to WhatsApp > Configuration > Templates**
2. **Click Create**
3. **Template Details:**
   - **Template Name**: Unique identifier (e.g., "order_confirmation")
   - **Language**: Select language
   - **Category**: Marketing, Utility, or Authentication
   - **Header Type**: None, Text, Image, Video, or Document
   - **Body**: Your message content
     - Use `{{1}}`, `{{2}}` for variables
     - Example: "Hello {{1}}, your order {{2}} has been confirmed!"
   - **Footer**: Optional footer text
   - **Buttons**: Add quick reply or call-to-action buttons

4. **Click Save**
5. **Submit to Meta for approval** (done through Meta Business Suite)

---

## Bulk Messaging

### Creating a WhatsApp Campaign

**Use Cases:**
- Product launches
- Promotional offers
- Event invitations
- Customer surveys
- Newsletter broadcasts

**Step-by-Step Guide:**

1. **Navigate to WhatsApp > Campaigns**
2. **Click Create**

3. **Campaign Configuration:**

   **Basic Information:**
   - **Campaign Name**: Descriptive name (e.g., "Summer Sale 2026")
   - **WhatsApp Account**: Select your account
   - **Campaign Type**: 
     - **Broadcast**: One-time message to all
     - **Drip Campaign**: Series of messages over time
     - **Event Triggered**: Automatic based on actions

   **Target Audience:**
   - **Target Type**: Choose how to select recipients
     - **All Contacts**: Everyone with a phone number
     - **Segmented**: Filter by specific criteria
     - **Manual Selection**: Pick specific contacts
     - **CRM Stage**: Based on pipeline stage
     - **Tags**: Based on contact tags

   **Segmentation Examples:**
   ```
   For customers in Mumbai:
   [('city', '=', 'Mumbai')]
   
   For customers who purchased in last 30 days:
   [('create_date', '>=', '2026-01-01')]
   
   For VIP customers:
   [('category_id.name', '=', 'VIP')]
   ```

4. **Message Content:**
   - **Template**: Select approved template (recommended)
   - **Message Body**: Or write custom text
   - Use variables: `{{name}}`, `{{company}}` for personalization

5. **Scheduling:**
   - **Send Immediately**: Sends right away
   - **Schedule**: Pick date and time for future sending

6. **Click Save**

7. **Load Recipients:**
   - Click **Load Recipients** button
   - System will show total count

8. **Launch Campaign:**
   - Review everything
   - Click **Send Campaign** button
   - Confirm the action

### Monitoring Campaign Performance

1. **Open your campaign**
2. **View Statistics:**
   - **Total Recipients**: Number of contacts targeted
   - **Sent**: Messages successfully sent
   - **Delivered**: Messages delivered to phones
   - **Read**: Messages opened by recipients
   - **Failed**: Messages that couldn't be sent
   - **ROI %**: Return on investment percentage

3. **View Individual Messages:**
   - Click on **Messages** tab
   - See status of each message
   - Filter by status (Sent, Delivered, Failed, etc.)

### Best Practices for Bulk Messaging

✅ **DO:**
- Get customer consent before messaging
- Send messages during business hours (9 AM - 6 PM)
- Personalize messages with customer names
- Keep messages concise and clear
- Include opt-out instructions
- Test with small group first
- Use approved templates for marketing

❌ **DON'T:**
- Send spam or unsolicited messages
- Message too frequently (max 1-2 per week)
- Send messages late at night
- Use all caps or excessive emojis
- Send messages without clear purpose
- Ignore customer opt-out requests

---

## Contact Management

### Adding New Contacts

1. **Navigate to Contacts**
2. **Click Create**
3. **Fill in Contact Information:**
   - **Name**: Full name (required)
   - **Company**: Company name
   - **Phone**: Primary phone number
   - **Mobile**: WhatsApp number (important!)
   - **Email**: Email address
   - **Address**: Full address details
   - **Tags**: Categorize (VIP, Lead, Customer, etc.)
   - **Notes**: Additional information

4. **Click Save**

### Importing Contacts in Bulk

1. **Navigate to Contacts**
2. **Click on Favorites (☆) > Import Records**
3. **Download Template:**
   - Click **Download Template**
   - Open in Excel/Google Sheets

4. **Fill in Contact Data:**
   - Name (required)
   - Mobile (for WhatsApp)
   - Email
   - Other fields as needed

5. **Upload File:**
   - Click **Upload File**
   - Select your filled template
   - Click **Import**

6. **Map Fields:**
   - Match your columns to Odoo fields
   - Click **Import**

### Organizing Contacts with Tags

1. **Create Tags:**
   - Go to Contacts > Configuration > Contact Tags
   - Click Create
   - Enter tag name (e.g., "VIP", "Lead", "Active Customer")
   - Choose color for visual identification

2. **Apply Tags to Contacts:**
   - Open contact
   - Click on **Tags** field
   - Select or create tags
   - Save

3. **Filter by Tags:**
   - In Contacts list view
   - Use **Filters** dropdown
   - Select tag to filter

---

## Discuss (Chat)

### Internal Team Communication

1. **Access Discuss:**
   - Click **Discuss** icon (chat bubble) in top menu
   - Or navigate to Discuss from main menu

2. **Channels:**
   - **#general**: Company-wide announcements
   - **#random**: Casual conversations
   - Create custom channels for teams/projects

3. **Direct Messages:**
   - Click on team member's name
   - Type message
   - Press Enter to send

4. **Creating Channels:**
   - Click **+** next to Channels
   - Enter channel name
   - Choose privacy (Public/Private)
   - Add members
   - Click Create

5. **Mentions:**
   - Type `@` followed by name to mention someone
   - They'll receive a notification

---

## Best Practices

### CRM Best Practices

1. **Update Regularly:**
   - Log all customer interactions
   - Update opportunity stages promptly
   - Keep contact information current

2. **Use Activities:**
   - Always schedule next activity
   - Set reminders for follow-ups
   - Track all communications

3. **Qualify Leads:**
   - Move unqualified leads to "Lost" with reason
   - Focus on high-probability opportunities
   - Use tags to prioritize

### WhatsApp Marketing Best Practices

1. **Compliance:**
   - Only message customers who opted in
   - Respect Meta's messaging policies
   - Include business name in messages
   - Provide opt-out option

2. **Timing:**
   - Send during business hours
   - Consider time zones
   - Avoid weekends for business messages

3. **Content:**
   - Keep messages under 160 characters when possible
   - Use emojis sparingly (1-2 per message)
   - Include clear call-to-action
   - Personalize with customer name

4. **Response Management:**
   - Enable AI auto-reply for common questions
   - Respond to customer messages within 24 hours
   - Monitor message delivery rates

### Data Management

1. **Regular Backups:**
   - Contact your administrator for backup schedule
   - Export important data periodically

2. **Data Quality:**
   - Remove duplicate contacts
   - Update outdated information
   - Verify phone numbers before campaigns

3. **Privacy:**
   - Don't share customer data externally
   - Follow data protection regulations
   - Keep access credentials secure

---

## Troubleshooting

### WhatsApp Messages Not Sending

**Check:**
1. WhatsApp account status is "Connected"
2. Phone number format includes country code (+91...)
3. Template is approved by Meta (for template messages)
4. Access token is valid
5. Customer hasn't blocked your number

**Solution:**
- Click **Test Connection** in WhatsApp Account
- Verify phone number format
- Check Meta Business Suite for template status
- Contact administrator if issues persist

### Campaign Shows 0 Recipients

**Check:**
1. Target type is correctly configured
2. Contacts have phone numbers filled
3. Domain filter is correct (if using segmented)

**Solution:**
- Click **Load Recipients** again
- Verify contacts have mobile numbers
- Try "All Contacts" to test

### Can't See Certain Menus

**Note:** Only administrators can access:
- Apps menu
- Technical settings
- Module installation

This is by design to protect system integrity.

---

## Quick Reference

### Common Tasks Checklist

**Daily:**
- [ ] Check new leads in CRM
- [ ] Respond to WhatsApp messages
- [ ] Update opportunity stages
- [ ] Complete scheduled activities

**Weekly:**
- [ ] Review pipeline health
- [ ] Plan WhatsApp campaigns
- [ ] Clean up lost opportunities
- [ ] Update contact information

**Monthly:**
- [ ] Analyze campaign performance
- [ ] Review won/lost ratio
- [ ] Update sales forecasts
- [ ] Archive old conversations

---

## Support

For technical support or questions:
- Contact your system administrator
- Email: support@your-company.com
- Phone: Your support number

---

**Document Version:** 1.0  
**Last Updated:** January 31, 2026  
**System:** ELSX CRM & WhatsApp Marketing Platform
