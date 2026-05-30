# FiberaFRP WhatsApp Marketing & CRM User Guide

## 1. Purpose

This guide explains how to use the WhatsApp Marketing system integrated with Odoo CRM. It is written for sales, support, marketing, and admin users who send WhatsApp messages, manage chats, run campaigns, create templates, and connect WhatsApp conversations with CRM leads, quotations, invoices, and customer records.

## 2. What This System Does

The WhatsApp Marketing system allows your team to:

- Manage all customer WhatsApp conversations from the Team Inbox.
- Send normal text messages, media, documents, and approved WhatsApp templates.
- Send catalogues, invoices, payment reminders, and campaign broadcasts.
- Send URL call-to-action buttons, catalogue/product messages, and shop links where configured.
- Connect WhatsApp chats with CRM leads, customers, quotations, and invoices.
- Run campaigns using contacts, tags, CRM stages, segments, or CSV uploads.
- Use bot flows to automate replies, route leads, assign agents, create CRM records, and collect customer responses.
- Use AI only as a draft assistant for replies, campaigns, templates, summaries, and flow reviews.
- Track sent, delivered, read, failed, and replied messages.
- Maintain opt-in, compliance, webhook, and Meta API health information.

## 3. Important Terms

| Term | Meaning |
|---|---|
| WhatsApp Account | The connected WhatsApp Business API number used for sending and receiving messages. |
| Team Inbox | The live chat screen where agents reply to customers. |
| Contact / Partner | The Odoo customer record linked to a WhatsApp number. |
| Template | A Meta-approved WhatsApp message used for marketing, utility, or authentication messages. |
| Placeholder | A reusable value such as `{{name}}`, `{{phone}}`, or `{{invoice_due_date}}` that is replaced during preview/send. |
| Session Open | The customer has messaged recently, so free-form replies are allowed. |
| Session Closed | The 24-hour WhatsApp window is closed. You must send an approved template. |
| Campaign | A bulk WhatsApp send to a selected audience. |
| Segment | A saved audience group based on tags, engagement, filters, or manual contacts. |
| Bot Flow | A visual automation that sends messages, waits for replies, creates leads, assigns agents, or routes customers. |
| Catalogue / Product Message | A WhatsApp commerce message that opens a catalogue, one product card, or a product list. |
| URL Button | A WhatsApp interactive call-to-action button that opens a configured web page. |
| AI Provider | The configured LLM endpoint used for draft suggestions, for example OpenAI-compatible APIs, Claude, NIM, DeepSeek, Qwen, HuggingFace, local/custom HTTP, or rules fallback. |
| Webhook | The Meta callback that brings inbound messages and delivery/read updates into Odoo. |

## 4. Prerequisites Before Using the System

Before users start sending messages, an admin must confirm the following:

| Requirement | Why It Is Needed |
|---|---|
| Meta WhatsApp Business Account | Required to use WhatsApp Cloud API. |
| Approved WhatsApp Business phone number | Messages are sent from this number. |
| Phone Number ID | Meta API identifier for the WhatsApp phone number. |
| Business Account ID | Meta WABA ID used for template sync and account health. |
| Access Token | Allows Odoo to call Meta APIs. |
| Webhook URL configured in Meta | Allows inbound messages and delivery/read updates. |
| Webhook Verify Token | Used when Meta verifies the webhook. |
| App Secret | Used for webhook signature security. |
| Approved message templates | Required for marketing messages and closed-session chats. |
| Contacts with WhatsApp numbers | Recipients must have valid phone numbers with country code. |
| Customer opt-in | Customers should have permission/consent for WhatsApp messaging. |
| CRM records | Needed if chats should create leads, quotes, invoices, or partner history. |
| Commerce Catalog ID | Required if sending catalogue or product messages. |
| Product Retailer IDs | Required for single-product and multi-product WhatsApp messages. |
| Shop URL | Required if flows or templates use a URL button to open the shop/catalogue page. |
| AI provider setup | Optional. Required only for AI draft reply, campaign copy, template draft, or flow review. |

Recommended phone format for India: `91XXXXXXXXXX`, without spaces, dashes, or symbols.

AI safety rule: AI suggestions are draft-only by default. A user must review and send/apply the draft manually.

# PART A: Daily User Guide

## 5. Opening WhatsApp Marketing

1. Log in to Odoo.
2. Open **WhatsApp Marketing** from the top menu.
3. Use the main sections:
   - **Engage**
   - **Campaigns**
   - **Automation**
   - **Analytics**
   - **Compliance**
   - **Configuration**

Each major screen includes a short guide or helper panel near the configuration area. Use these panels when setting up required Meta IDs, templates, catalogue IDs, placeholders, AI providers, or reply actions.

Most daily users will mainly use **Engage > Team Inbox**.

## 6. Team Inbox

### 6.1 What Team Inbox Is Used For

Team Inbox is used to handle customer conversations in one place.

Use it to:

- Read incoming WhatsApp messages.
- Reply to customers.
- Send approved templates.
- Attach media or documents.
- Assign chats to agents.
- Add labels/tags.
- Create CRM leads.
- Open customer profiles.
- Create quotations or invoices.
- Resolve or reopen conversations.

### 6.2 Opening Team Inbox

1. Go to **WhatsApp Marketing > Engage > Team Inbox**.
2. Select the WhatsApp account if required.
3. Use filters:
   - **All**: all conversations.
   - **Open**: active conversations.
   - **Unread**: chats with unread customer messages.
   - **Mine**: chats assigned to you.
   - **Unassigned**: chats not assigned to any agent.

### 6.3 Understanding the Chat Screen

| Area | Purpose |
|---|---|
| Left sidebar | Chat list, filters, search, account selector. |
| Center panel | Customer conversation and message composer. |
| Right panel | Customer profile, assigned agent, CRM details, orders, invoices. |
| Template button | Send approved WhatsApp template. |
| Send button | Send typed message or selected content. |
| Attachment/media buttons | Add file, document, image, or media where available. |

### 6.4 Chat Status

| Status | Meaning |
|---|---|
| Open | Conversation is active and needs attention. |
| Resolved | Conversation is completed. |
| Snoozed | Conversation is temporarily hidden or paused. |
| Archived | Conversation is stored but not active. |
| SLA Breach | Customer has waited longer than the expected response time. |

### 6.5 Session Open vs Session Closed

WhatsApp has a 24-hour customer service window.

| Session | What You Can Send |
|---|---|
| Session Open | Free text, media, normal replies, templates. |
| Session Closed | Only approved Meta templates. |

If the chat input says the session is closed, send a template instead of typing a normal message.

## 7. Sending Messages from Team Inbox

### 7.1 Send a Normal Text Message

Use this when the customer session is open.

1. Open the customer chat.
2. Type the message in the message box.
3. Click **Send**.

Example:

```text
Hello, thank you for contacting FiberaFRP. How can we help you today?
```

### 7.2 Send a Template Message

Use this when:

- The session is closed.
- You are sending a marketing, utility, invoice, or follow-up message.
- You need to send an approved standard message.

Steps:

1. Open the chat.
2. Click **Template**.
3. Select the approved template.
4. Review the preview.
5. If the template has a document, image, or video header, attach the required file if needed.
6. Click **Send**.

### 7.3 Send a Document Header Template

Some templates require a document in the header, for example a catalogue or invoice PDF.

Requirements:

- The template header type must be **Document**.
- A PDF/document must be supplied.
- The document can come from:
  - Template default document.
  - Per-send attachment in the wizard.
  - Invoice PDF if sending from invoice workflow.

If no document is supplied, WhatsApp will reject the message.

Common error:

```text
Document header templates require a media handle or public URL before sending.
```

Fix:

1. Open the template.
2. Upload a default header document, or
3. Attach the PDF while sending, or
4. For invoices, enable **Attach Invoice PDF**.

### 7.4 Send Media

Use media for images, PDFs, catalogues, product sheets, or videos.

1. Open chat.
2. Attach the file if the option is available.
3. Add an optional caption.
4. Click **Send**.

Meta media limits:

| Media Type | Limit |
|---|---|
| Image | Up to 5 MB |
| Video | Up to 16 MB |
| Audio | Up to 16 MB |
| Document | Up to 100 MB |
| Text message | Up to 4096 characters |
| Media caption | Up to 1024 characters |

### 7.5 Send URL Button or Shop Link

Use a URL button when the customer should open a website, shop page, catalogue download page, payment link, or product page.

Required:

- Button text, for example `Open Catalogue`.
- URL beginning with `https://`.
- Short message text explaining what the button opens.

Example:

```text
Please open our product catalogue below.
Button: Open Catalogue
URL: https://fiberafrp.example.com/catalogue
```

### 7.6 Send Catalogue or Product Messages

Catalogue/product messages require commerce setup on the WhatsApp account.

Required values:

| Message Type | Required Configuration |
|---|---|
| Full catalogue | Catalog ID and message text. |
| Single product | Catalog ID and product retailer ID. |
| Multi-product list | Catalog ID, section title, and up to 30 product retailer IDs grouped into rows. |

If the catalogue message fails, check:

- The account has a valid Meta Commerce Manager Catalog ID.
- Product retailer IDs match the IDs inside Meta Commerce Manager.
- The product is available and connected to the WhatsApp Business Account.
- The customer can receive interactive WhatsApp messages.

## 8. CRM Actions from Team Inbox

### 8.1 View Partner

Use **View Partner** to open the customer's Odoo contact record.

Use this to check:

- Name
- Phone
- Email
- Company
- Tags
- WhatsApp opt-in
- Sales history
- Invoices
- Message history

### 8.2 Create Opportunity

Use this when the chat is a sales enquiry.

1. Open the customer chat.
2. Click **Create Opportunity** or the CRM action.
3. Confirm customer details.
4. Save the lead/opportunity.

Example use cases:

- Customer asks for FRP manhole cover pricing.
- Customer asks for catalogue.
- Customer wants dealer/distributor details.
- Customer requests quotation.

### 8.3 Create Quote

Use this when the customer is ready for pricing.

1. Open the chat.
2. Click quotation/order action if available.
3. Add products and quantities.
4. Save or send quotation.

### 8.4 Invoice WhatsApp Send

Use this from invoice screens.

1. Open the invoice.
2. Click **Send WhatsApp Invoice**.
3. Select WhatsApp account.
4. Select approved invoice template.
5. Keep **Attach Invoice PDF** enabled if needed.
6. Send.

If the template has a document header, the invoice PDF is sent inside the template header instead of as a duplicate separate PDF.

### 8.5 AI Draft Assistance in Team Inbox

Use **Draft AI Reply** only as an assistant. It can suggest:

- Reply text.
- Customer intent.
- Sentiment and urgency.
- Summary.
- Suggested tags.
- Suggested next action or flow handoff.

AI does not send the message automatically. Review the draft, edit it if needed, then send manually.

# PART B: Campaigns

## 9. Campaign Overview

Go to **WhatsApp Marketing > Campaigns > All Campaigns**.

Use campaigns for:

- Product promotions
- Catalogue broadcasts
- Dealer outreach
- Payment reminders
- Event announcements
- Lead nurturing
- Customer reactivation
- Follow-up sequences

## 10. Creating a Campaign

1. Go to **Campaigns > All Campaigns**.
2. Click **New**.
3. Enter **Campaign Name**.
4. Select **WhatsApp Account**.
5. Select **Campaign Type**.
6. Select **Target Type**.
7. Configure recipients.
8. Configure message content.
9. Click **Load Recipients**.
10. Review total recipients.
11. Click **Schedule / Send**.

## 11. Campaign Types

| Campaign Type | Meaning | When to Use |
|---|---|---|
| Broadcast | One-time message to many contacts. | Catalogue, promotion, announcement. |
| Drip Campaign | Multi-step sequence over time. | Follow-up series, nurturing. |
| Event Triggered | Starts from an event. | Future automation use. |
| Conversational | Conversation-style campaign. | Support/sales engagement. |

Most marketing users should use **Broadcast** unless they specifically need a sequence.

## 12. Target Types

| Target Type | Meaning | Requirement |
|---|---|---|
| All Contacts | Sends to all eligible contacts. | Contacts must have WhatsApp numbers. |
| Segment | Sends to a saved audience segment. | Select segment or domain filter. |
| Manual Selection | User selects contacts manually. | Add recipients in Recipients tab. |
| CRM Stage | Sends to leads in a CRM stage. | Select CRM stage. |
| Tags | Sends to contacts with selected tags. | Select tags. |
| CSV Upload | Imports audience from CSV. | CSV must include phone/name columns. |

Recommended: use **Segment** or **Tags** for controlled campaigns.

## 13. Loading Recipients

Before sending:

1. Configure target type.
2. Click **Load Recipients**.
3. Confirm total recipients.
4. Check that recipients have valid phone numbers.
5. Remove invalid or unwanted contacts if needed.

If no recipients are loaded, the campaign cannot send.

## 14. Campaign Message Tab

Use the **Message** tab for normal broadcast content.

You can choose either:

| Option | Meaning |
|---|---|
| Message Template | Use approved Meta template. Recommended for marketing and closed sessions. |
| Message Body | Use plain text message. Use only where allowed. |

Example text body:

```text
Dear {{name}}, we are excited to introduce FiberaFRP drainage solutions. Please reply if you want our catalogue.
```

Supported personalization in campaigns may include:

```text
{{name}}
{{company}}
```

Always test personalization before sending a large campaign.

## 15. A/B Testing

Use A/B Testing to compare two campaign messages.

Go to the **A/B Testing** tab.

Steps:

1. Enable **A/B Testing**.
2. Configure Version A:
   - Template A or Message Body A.
3. Configure Version B:
   - Template B or Message Body B.
4. Set split percentage.
5. Load recipients.
6. Send campaign.
7. Review read rate and delivery results.
8. Use **Determine Winner** when enough data is available.

Use A/B testing when comparing:

- Two catalogue introductions.
- Different call-to-action wording.
- Template vs text format.
- Different offers or product highlights.

## 15.1 Campaign Reply Actions

Use **Reply Actions** to decide what happens when a recipient replies to a campaign.

Supported reply handling can include:

| Reply Type | Possible Action |
|---|---|
| Template quick reply button | Start flow, send message, add tag, create lead, assign agent/team, set chat status, or no action. |
| Free-text reply | Start flow, assign agent/team, add tag, create/update lead note, or mark chat for human follow-up. |
| Unmatched reply | Use fallback action or assign to team. |

Before sending, sync reply buttons from the selected template and confirm every active rule has:

- Match type and match value.
- Action type.
- Required action target, such as flow, tag, user, team, or status.

## 15.2 AI Campaign Drafts

Use **Draft Content** to ask AI for a campaign draft, A/B variants, audience-fit warning, spam-risk warning, and reply-rule suggestions.

AI campaign drafts are not sent automatically. A user must review the content, confirm opt-in/compliance, load recipients, and send the campaign manually.

## 16. Scheduling a Campaign

Campaign schedule options:

| Schedule | Meaning |
|---|---|
| Send Immediately | Queue and start sending now. |
| Scheduled | Send at selected date/time. |

Steps:

1. Select schedule type.
2. For scheduled campaigns, choose scheduled date/time.
3. Click **Schedule / Send**.

## 17. Campaign Sending and Queue

Campaigns use safe sending.

Important fields:

| Field | Meaning |
|---|---|
| Batch Size | Number of messages sent per batch. |
| Batch Interval | Time between batches. |
| Queued | Messages waiting to send. |
| Sent | Messages sent to Meta. |
| Delivered | Messages delivered to customer. |
| Read | Customer opened/read the message. |
| Failed | Message failed. |

If a campaign is running, admins may see **Process Queue (Send 50)**.

## 18. Campaign Result Review

Open the campaign and check:

- Total Recipients
- Queued
- Sent
- Delivered
- Read
- Failed
- Delivery Rate
- Read Rate
- Messages tab
- Participants tab
- Analytics tab

If many messages fail, check:

- Template approval status.
- Recipient phone format.
- Meta quality rating.
- Daily messaging limit.
- Missing media/document header.
- Customer opt-in/compliance.
- API/webhook errors.

# PART C: Templates

## 19. Template Overview

Go to **WhatsApp Marketing > Campaigns > My Templates**.

Use templates for:

- Marketing broadcasts
- Utility messages
- Invoice messages
- Payment reminders
- Catalogue messages
- Closed-session conversations
- Authentication/OTP

## 20. Template Status

| Status | Meaning |
|---|---|
| Draft | Created in Odoo but not approved. |
| Pending Approval | Sent to Meta and waiting. |
| Approved | Can be sent. |
| Rejected | Cannot be sent until corrected. |

Only **Approved** templates should be used for sending.

## 21. Template Categories

| Category | Use |
|---|---|
| Marketing | Promotions, catalogues, offers, announcements. |
| Utility | Order updates, invoices, payment reminders, service updates. |
| Authentication | OTP or login verification. |

Choose the correct category. Wrong categories may get rejected or restricted by Meta.

## 22. Template Fields

| Field | Meaning |
|---|---|
| Template Name | Internal/template name. Should match Meta-approved name where needed. |
| Meta Template Name | Exact name approved in Meta. |
| Language | Template language. |
| Exact Language Code | Meta locale code such as `en`, `en_US`, `hi_IN`. |
| Header Type | None, Text, Image, Video, or Document. |
| Header Text | Header line if header type is Text. |
| Header Media URL | Public URL or Meta media reference for media headers. |
| Header Media File | Default file used for image/video/document header. |
| Body | Main message content. |
| Footer | Optional footer text. |
| Buttons | Quick reply, call-to-action, or copy-code buttons. |
| Attributes Mapping | Variable samples and Odoo field mappings. |

## 23. Template Variables / Attributes

Meta template variables use numbered placeholders:

```text
{{1}}, {{2}}, {{3}}
```

Example:

```text
Dear {{1}}, your invoice {{2}} is ready. Total amount is {{3}}.
```

Requirements:

- Variables must be sequential.
- Do not skip numbers.
- Correct: `{{1}}, {{2}}, {{3}}`
- Wrong: `{{1}}, {{3}}`
- Every variable needs a sample value.
- Sample values are required for Meta approval.
- Variables can map to Odoo fields where configured.

Example mapping:

| Variable | Sample Value | Possible Field |
|---|---|---|
| `{{1}}` | Shashank Patel | `partner_id.name` |
| `{{2}}` | INV/2026/001 | `invoice_id.name` |
| `{{3}}` | Rs. 25,000 | invoice total field |

For normal message previews, campaigns, flows, and AI prompts, use the **Placeholder Guide** to see supported placeholders, examples, and allowed contexts.

Common placeholders:

```text
{{name}}
{{phone}}
{{company}}
{{email}}
{{last_reply}}
{{record_name}}
{{amount_total}}
{{invoice_due_date}}
{{opportunity_name}}
{{customer_requirement}}
```

Always preview placeholders against a real contact or sample record before bulk sending.

## 24. Header Types

| Header Type | Requirement |
|---|---|
| None | No header required. |
| Text | Add header text. |
| Image | Add image media file or URL. |
| Video | Add video media file or URL. |
| Document | Add document/PDF file or URL. |

Document-header templates must always send a document.

Example catalogue template:

- Header Type: Document
- Header File: Fibera catalogue PDF
- Body: Introductory message
- Button: Optional CTA

## 25. Buttons

| Button Type | Use |
|---|---|
| Quick Reply | Customer taps a reply option. |
| Call to Action | Opens a URL or phone call. |
| Copy Code | OTP/authentication use. |
| Catalogue/Product | Opens a configured shop, catalogue, single product, or product list where supported. |

Examples:

Quick Reply:

```text
Interested
Need Catalogue
Talk to Sales
```

CTA URL:

```text
Visit Website
Download Catalogue
```

CTA Phone:

```text
Call Sales Team
```

URL CTA:

```text
Open Catalogue
https://fiberafrp.example.com/catalogue
```

Catalogue/product button configuration needs the account Catalog ID and product retailer IDs.

## 26. Template Preview

Use template preview before sending.

Check:

- Header is visible.
- Body text is correct.
- Variables show sample values.
- Buttons are correct.
- Document/image/video is attached if required.
- Message does not look incomplete.

The complete preview should show:

- Header text, image, video, or document filename/warning.
- Body with resolved variables.
- Footer.
- Quick replies.
- CTA URL/phone/copy-code buttons.
- Carousel cards if configured.

## 26.1 AI Template Draft

Use **AI Draft Body** to generate a suggested template body and Meta-format warnings.

Rules:

- AI only drafts text; it does not submit to Meta.
- Check variables, samples, language code, category, media header, and buttons manually.
- Use preview before requesting approval or sending a test.

## 27. Common Template Errors

| Error | Meaning | Fix |
|---|---|---|
| Template not approved | Meta has not approved it. | Use approved template only. |
| Missing sample values | Variables do not have samples. | Fill Attributes Mapping. |
| Variables not sequential | Placeholder numbers skipped. | Use `{{1}}, {{2}}, {{3}}`. |
| Missing document header | Document template has no file/URL. | Upload or attach PDF. |
| Wrong language code | Meta cannot find template language. | Use exact approved code. |
| Rejected by Meta | Template violates policy or format. | Check rejection reason and revise. |

# PART D: Contact Segments

## 28. Audience Segments

Go to **WhatsApp Marketing > Campaigns > Audience Segments**.

Segments are saved recipient groups.

Use segments for:

- Dealers
- Existing customers
- Leads by interest
- Inactive customers
- High engagement contacts
- Customers by tag
- Customers by geography

## 29. Segment Types and Filters

| Filter | Meaning |
|---|---|
| Manual Contacts | Specific selected contacts. |
| Tags | Contacts with selected tags. |
| All Tags | Contacts must have all selected tags. |
| Exclude Tags | Remove contacts with selected tags. |
| Message Count | Filter by engagement volume. |
| Last Message Days | Customers who messaged recently. |
| Inactive Days | Customers inactive for selected days. |
| Engagement Level | Low, medium, or high engagement. |
| Country Code | Filter by country. |
| Lifetime Value | Filter by customer value. |
| Domain Filter | Advanced Odoo filter. |

After changing a segment, click **Refresh Contacts** if available.

# PART E: Automation and Bot Flow Builder

## 30. Flow Builder Overview

Go to **WhatsApp Marketing > Automation > Flow Builder**.

Bot flows automate WhatsApp conversations.

Use flows for:

- Welcome messages
- Support menu
- Lead qualification
- Product enquiry routing
- Feedback collection
- Assigning agents
- Creating CRM leads
- Adding labels
- Waiting for customer replies
- Sending multi-step sequences

## 31. Flow Settings

| Field | Meaning |
|---|---|
| Flow Name | Internal name for the automation. |
| WhatsApp Account | Account used to send flow messages. |
| Flow Type | Purpose such as support, sales, survey, custom. |
| Trigger | What starts the flow. |
| Keywords | Words that trigger the flow. |
| Priority | Higher priority flows run first. |
| Active | Only active flows run automatically. |
| Retry on Failure | Retry failed steps. |
| Max Retries | Maximum retry attempts. |

## 32. Trigger Types

| Trigger | Meaning |
|---|---|
| Keyword Match | Starts when customer sends matching word. |
| First Message | Starts for new customer conversation. |
| Manual Trigger | Started manually. |
| Scheduled | Runs based on schedule pattern. |
| Webhook Event | Starts from internal/external event. |

Example keywords:

```text
hello, hi, start, support, catalogue, price
```

## 33. Visual Flow Builder vs Steps List

| Area | Purpose |
|---|---|
| Visual Flow Builder | Drag/drop style overview of flow nodes and connections. |
| Steps List | Detailed list of executable steps. |
| Step Form / View | Full configuration for each step. |

Recommended workflow:

1. Build the flow structure visually.
2. Open each step in detail.
3. Configure required fields.
4. Save.
5. Test flow.
6. Review logs.

## 34. Step Types and Meaning

### 34.1 Send Text Message

Use this to send a normal automated text.

Required:

- Message Text

Example:

```text
Hi {{name}}, how can we help you today?
```

Use when greeting customers, asking questions, or sharing simple instructions.

### 34.2 Send Template

Use this to send an approved WhatsApp template.

Required:

- Template

Use when:

- Session may be closed.
- Sending approved marketing/utility content.
- Sending structured message from Meta template.

Important:

- Template must be approved.
- Media/document header templates need required media.

### 34.3 Send Media

Use this to send a file, image, catalogue, video, or document.

Required:

- Media

Optional:

- Message/caption text

Use when sending a product catalogue, brochure, image, or product sheet.

### 34.3.1 Send URL Button

Use this to send one interactive button that opens a configured URL.

Required:

- Message text.
- Button text.
- HTTPS URL.

Use cases:

- Open catalogue page.
- Open shop page.
- Open payment link.
- Open product details page.

### 34.3.2 Send Catalogue / Product

Use this to send commerce messages from Meta Commerce Manager.

Supported modes:

| Mode | Required Fields |
|---|---|
| Full Catalogue | Catalog ID and message text. |
| Single Product | Catalog ID and product retailer ID. |
| Multi-Product List | Catalog ID, section title, and product retailer IDs. |

Recommended setup:

1. Add Catalog ID on the WhatsApp Account.
2. Add default product retailer ID if one product is commonly used.
3. In the flow step, choose full catalogue, single product, or product list.
4. Test with an internal WhatsApp number.

### 34.4 Send Buttons / Quick Replies

Use this to show selectable customer options.

Required:

- Message Text
- At least one button row

Button fields:

| Field | Meaning |
|---|---|
| Button Text | Text customer sees. |
| Button ID | Internal button identifier. |
| Button Action | Reply, URL, or catalog product. |
| URL | Web page opened when action is URL. |
| Catalog ID | Meta catalog used when action is catalog product. |
| Product Retailer ID | Meta product ID used when action is catalog product. |
| Go To Step | Step to run when customer selects the button. |

Example:

```text
How can we help?

1. Product Catalogue
2. Price Enquiry
3. Talk to Sales
```

Quick reply buttons are limited to 3 options. List rows are limited to 10 rows per menu.

### 34.5 Wait for Response

Use this to pause the flow until the customer replies.

Useful fields:

| Field | Meaning |
|---|---|
| Save Response | Save customer reply. |
| Response Variable | Variable name for later use. |

Example response variable:

```text
customer_requirement
```

Use when asking customers for product size, city, order number, or feedback.

### 34.6 Conditional Logic

Use this to route based on customer reply or variable.

Required:

- Condition Type
- Condition Value
- Go To If True and/or Go To If False

Condition examples:

| Condition Type | Use |
|---|---|
| Keyword Match | Reply exactly or mostly matches keyword. |
| Response Contains | Reply contains selected text. |
| JSON Path / Variable | Checks stored variable value. |

Example: if customer reply contains `price`, go to **Price Enquiry Step**.

### 34.7 Assign Agent

Use this to assign a chat to a team member.

Required:

- Assigned User

Use when the customer needs human support, sales handover, or complaint handling.

### 34.8 Add Tag / Label

Use this to label the customer or conversation.

Required:

- Tag

Examples:

```text
Hot Lead
Catalogue Sent
Support Required
Dealer Enquiry
Payment Follow-up
```

Use tags for future filtering and campaign targeting.

### 34.9 Create Lead

Use this to create a CRM opportunity from the WhatsApp chat.

Optional:

- Message text / note

Use when:

- Customer shows buying intent.
- Customer asks for pricing.
- Customer requests sales callback.
- Customer shares project requirement.

### 34.10 HTTP Request

Use this to call an external API or webhook.

Required:

- HTTP Method
- URL

Optional:

- JSON Payload
- Response Variable

Use when sending customer data to another system, checking order status, or triggering an external workflow. Only admins should configure this step.

### 34.11 Set Variable

Use this to store a reusable value in the flow.

Required:

- Variable Name
- Variable Value

Example:

```text
interest = FRP Manhole Cover
```

Use when storing customer selections, reusing reply values, or passing data to later message/API steps.

### 34.12 Delay

Use this to pause before the next step.

Required:

- Delay seconds

Rules:

- Delay cannot be negative.
- Maximum supported delay is 86400 seconds, meaning 24 hours.

Examples:

| Delay | Seconds |
|---|---|
| 5 seconds | `5` |
| 5 minutes | `300` |
| 1 hour | `3600` |
| 24 hours | `86400` |

### 34.13 End

Use this to stop the flow.

Use when the conversation is completed, no further automation is needed, or the customer has been handed over to an agent.

## 35. Flow Placeholders

Flow messages can use placeholders.

Examples:

```text
{{name}}
{{partner_name}}
{{customer_name}}
{{phone}}
{{phone_number}}
{{mobile}}
{{email}}
{{company}}
{{company_name}}
{{last_message}}
{{last_reply}}
```

Example message:

```text
Hi {{name}}, thank you for contacting FiberaFRP. Please share your requirement.
```

Always test the flow to make sure placeholders are replaced correctly.

## 36. Testing a Flow

1. Open the flow.
2. Check all steps have required fields.
3. Click **Test Flow**.
4. Send a matching keyword from WhatsApp.
5. Confirm the correct messages are sent.
6. Check if buttons route correctly.
7. Check if lead/tag/assignment is created.
8. Open **Execution Logs** to review success or failure.

# PART F: Analytics and Message Tracking

## 37. Analytics Dashboard

Go to **WhatsApp Marketing > Analytics > Dashboard**.

Use analytics to review:

- Sent messages
- Delivered messages
- Read messages
- Failed messages
- Campaign performance
- Agent/team performance
- Account usage and limits

## 38. Message Status Meaning

| Status | Meaning |
|---|---|
| Draft | Message created but not sent yet. |
| Queued | Waiting for safe sending. |
| Sent | Accepted by Meta. |
| Delivered | Delivered to customer device. |
| Read | Customer read/opened message. |
| Failed | Meta rejected or sending failed. |

If delivered/read updates do not appear, check webhook configuration and Meta webhook subscriptions.

# PART G: Compliance

## 39. Compliance and Consent

Go to **WhatsApp Marketing > Compliance**.

Use compliance settings to manage:

- Opt-in requirements
- Consent logs
- DND / opt-out contacts
- Message retention
- Quiet hours
- Audit logs
- Team permissions

Important:

- Do not send campaigns to customers who opted out.
- Respect STOP/UNSUBSCRIBE/OFF keywords.
- Keep customer consent records.
- Avoid sending irrelevant or excessive messages.

# PART H: Admin Configuration

## 40. WhatsApp Account Setup

Go to **WhatsApp Marketing > Configuration > WhatsApp Accounts**.

Important fields:

| Field | Meaning |
|---|---|
| Account Name | Internal account name. |
| Phone Number | WhatsApp business number. |
| Phone Number ID | Meta phone number ID. |
| Business Account ID | Meta WABA/business account ID. |
| Access Token | Meta Cloud API token. |
| API Version | Meta API version. |
| Default Country Code | Used when numbers do not include country code. |
| Meta Catalog ID | Commerce Manager catalog used for product cards and product lists. |
| Default Product Retailer ID | Default Meta catalog content ID/SKU used for product cards or catalog thumbnails. |
| Shop / Catalogue URL | Public URL used by URL button steps and catalogue call-to-action messages. |
| Commerce Manager URL | Internal admin link for maintaining the Meta product catalog. |
| Webhook URL | URL to paste into Meta webhook setup. |
| Webhook Verify Token | Token used by Meta verification. |
| App Secret | Used for signature validation. |
| Sandbox Mode | Test mode; only registered test numbers work. |
| Commerce Catalog ID | Meta catalog used for catalogue/product messages. |
| Default Product Retailer ID | Default product ID used by product-card flows. |
| Shop URL | Website/shop/catalogue URL used by URL buttons. |
| Commerce Manager URL | Admin reference link for catalog maintenance. |

After setup:

1. Click **Test Connection**.
2. Click **Sync from Meta** under Business Profile if needed.
3. Check quality rating and messaging limit.
4. Send a test message.
5. Confirm inbound webhook works.
6. Confirm delivered/read status updates appear.

### 40.1 Catalog and Shop Setup

Use this when you want WhatsApp bot flows or inbox messages to send product cards, product lists, or a shop/catalogue link.

Required:

- Meta Commerce catalog connected to the WhatsApp Business Account.
- Product Retailer ID / Content ID for each product you want to send.
- Public shop/catalogue URL if using URL buttons.

In Odoo:

1. Open **WhatsApp Marketing > Configuration > WhatsApp Accounts**.
2. Open the WhatsApp account.
3. Go to **Commerce / Shop**.
4. Fill **Meta Catalog ID**.
5. Fill **Default Product Retailer ID** if you have one common product to highlight.
6. Fill **Shop / Catalogue URL** for URL button flows.
7. Save.

Important: Product Retailer ID is the ID from Meta Commerce Manager, not the Odoo product database ID.

### 40.2 Tally Invoice Bridge Setup

Use this when posted Odoo invoices need to be exported or pushed into Tally.

Go to **Invoicing > Configuration > Settings > Tally Integration**.

Important fields:

| Field | Meaning |
|---|---|
| Enable Tally Bridge | Shows Tally XML and push actions on posted invoices. |
| Tally Gateway URL | Tally XML/HTTP gateway URL, commonly `http://host.docker.internal:9000` when Tally runs on the Windows host and Odoo runs in Docker. |
| Tally Company Name | Exact company name open in Tally. Leave blank to use the Odoo company name. |
| Sales Ledger | Tally ledger used for customer invoice sales amount. |
| Purchase Ledger | Tally ledger used for vendor bill purchase amount. |
| Tax Ledger | Tally ledger used for total tax amount. |
| Gateway Timeout Seconds | How long Odoo waits during direct push. |
| Auto Push Posted Customer Invoices | Keep off until tested; direct push happens automatically only when enabled. |

Recommended setup:

1. Open Tally.
2. Open the correct company.
3. Enable the Tally XML/HTTP gateway.
4. Confirm the required ledgers already exist in Tally.
5. Fill the Tally settings in Odoo.
6. Click **Test Tally Connection**.
7. Open a posted invoice.
8. Click **Tally XML** first and verify the XML import manually in Tally.
9. Use **Push to Tally** only after the manual XML path is confirmed.

Invoice buttons:

| Button | Purpose | Safe Use |
|---|---|---|
| Tally XML | Downloads a Tally import XML file and logs the export. | Use first; does not require live Tally connectivity. |
| Push to Tally | Sends the invoice XML to the configured Tally gateway. | Use only after settings and ledgers are tested. |
| Tally Logs | Opens request/response/error history for that invoice. | Use for troubleshooting. |
| Reset Tally Status | Clears Odoo's Tally status on the invoice. | Use before retrying after a failed/incorrect export. |

Common Tally notes:

- The customer/vendor name in Odoo should match or be creatable as a ledger in Tally.
- The configured Sales, Purchase, and Tax ledgers must exist in Tally.
- XML export is safer for the first client demo because it does not depend on network access from Docker to the Tally desktop.
- Direct push may fail if Tally is closed, the wrong company is open, the gateway is disabled, or the URL is unreachable from the Odoo server.

### 40.3 Hidden Apps Menu and Secret Admin URL

The standard Odoo **Apps** menu is hidden from normal navigation for client safety. It should not be used by daily users.

Apps access is available only to system administrators who know the secret URL:

```text
https://fibera.elsxglobal.com/elsx-secret/apps/<secret-token>
```

Rules:

- The user must be logged in.
- The user must be an Odoo system administrator.
- The token must match the system parameter `elsx_client_restrictions.apps_secret_token`.
- Old direct shortcut `/action-39` is blocked unless the same secret token is included.

Use this only for controlled technical maintenance, module updates, or app diagnostics.

## 41. Meta Health and Limits

Important account health fields:

| Field | Meaning |
|---|---|
| Quality Rating | Meta rating such as GREEN, YELLOW, RED. |
| Messaging Limit | Meta messaging tier. |
| Max Daily Limit | Daily send limit used by the system. |
| Daily Message Count | Messages sent today. |
| Daily Limit Remaining | Remaining quota. |
| Daily Limit Usage % | How much of the daily limit is used. |
| Throughput Level | Meta throughput information if available. |
| Last Webhook Received | Last inbound webhook time. |
| Last Delivery Status Webhook | Last delivered/read status update. |

If the limit is reached, messages may queue or fail.

## 42. Webhook Setup Checklist

In Meta Developer / Business Manager:

1. Add webhook callback URL from Odoo.
2. Add webhook verify token from Odoo.
3. Subscribe to WhatsApp message events.
4. Confirm verification succeeds.
5. Send test message from customer phone.
6. Confirm chat appears in Team Inbox.
7. Send reply from Odoo.
8. Confirm sent/delivered/read status updates.

## 42.1 AI Provider Setup

Go to **WhatsApp Marketing > Configuration > AI Providers**.

Supported provider styles:

| Provider Type | Notes |
|---|---|
| Rules Fallback | Local deterministic draft support. Use this when no LLM is configured. |
| OpenAI Compatible | Works with OpenAI-style `/v1/chat/completions` APIs. |
| Anthropic / Claude | Uses Anthropic message format. |
| NVIDIA NIM | Uses OpenAI-compatible NIM endpoints. |
| DeepSeek | Uses OpenAI-compatible DeepSeek endpoints. |
| Alibaba / Qwen | Uses DashScope/OpenAI-compatible Qwen endpoints when configured. |
| HuggingFace | Use with an inference endpoint or custom compatible API. |
| Local / Custom HTTP | Use for private/self-hosted models. |

Important provider fields:

| Field | Meaning |
|---|---|
| Provider Type | Selects request style and default endpoint behavior. |
| Base URL | Provider endpoint base URL. |
| API Key | Secret key/token. |
| API Key Header | Header name when provider does not use standard Authorization. |
| Model Name | Model to call. |
| Timeout / Retries | Prevents long hanging requests. |
| Temperature / Max Tokens | Controls response creativity and length. |
| Request Format | Chat completions, Anthropic messages, custom JSON, or rules. |
| Response Path | JSON path used to extract text for custom APIs. |
| Test Provider | Sends a test prompt and stores request/response status. |

Settings:

| Setting | Recommended Value |
|---|---|
| AI Enabled | Off until provider test succeeds. |
| AI Auto Write | Off. Users should approve AI output before business records change. |
| WhatsApp AI Drafts | On only after provider setup. |
| WhatsApp AI Auto Send | Off. Customer messages must be manually approved. |

## 42.2 Placeholder Guide

Go to **WhatsApp Marketing > Configuration > Placeholder Guide**.

Use this screen to check:

- Placeholder name.
- Sample value.
- Allowed context, such as global, chat, campaign, invoice, CRM, flow, or AI prompt.
- Meaning and recommended use.

Use placeholders in templates, campaign previews, flow messages, and AI prompt instructions.

# PART I: Troubleshooting

## 43. Common Problems and Fixes

| Problem | Cause | Fix |
|---|---|---|
| White screen | Frontend/view/asset issue. | Hard refresh, check Odoo logs, upgrade module if view changed. |
| Template not sending | Template not approved or wrong language. | Use approved template and exact language code. |
| Document header error | Required PDF/document missing. | Upload template header file or attach PDF while sending. |
| Message failed due to ecosystem engagement | Meta blocked delivery to protect ecosystem quality. | Reduce frequency, improve targeting, use opted-in users, avoid spam-like content. |
| Customer did not receive message | Wrong phone, blocked user, Meta rejection, or limit. | Check phone format, message status, API logs. |
| Delivered/read not updating | Webhook status callback missing. | Check webhook URL, subscriptions, app secret, account health. |
| Chat appears duplicated | Multiple message records or UI stale cache. | Hard refresh, check chat list after latest update. |
| Campaign has zero recipients | Audience filter found no contacts. | Check target type, tags, segment, CRM stage, CSV. |
| A/B testing not visible | Campaign is drip or tab not selected. | Use broadcast campaign and open A/B Testing tab. |
| Template preview incomplete | Missing variables or media. | Fill attributes and header media. |
| URL button fails | URL missing or not HTTPS. | Add a complete `https://` URL. |
| Catalogue/product message fails | Catalog ID or product retailer ID missing/wrong. | Check WhatsApp Account commerce fields and Meta Commerce Manager IDs. |
| AI draft not generated | AI disabled, no provider, provider test failed, timeout, or bad API key. | Enable AI after provider test succeeds and check AI job logs. |
| AI output not sent automatically | This is intentional. | Review and send/apply the draft manually. |
| Cannot send normal text | Session closed. | Send approved template. |
| Media upload failed | File too large or wrong type. | Check Meta size limits. |
| Rate limit exceeded | Account daily or token limit reached. | Wait, reduce batch size, check account limit. |
| Sandbox message failed | Recipient not registered in Meta test numbers. | Add number in Meta Developer test recipients. |
| Tally push failed | Tally gateway closed, wrong URL, wrong company, missing ledger, or Tally rejected XML. | Use Tally XML first, confirm ledgers/company, then retry Push to Tally and review Tally Sync Logs. |

# PART J: Best Practices

## 44. Messaging Best Practices

- Send only to opted-in customers.
- Keep messages short and useful.
- Avoid repeated promotional messages to the same user.
- Use templates for campaigns and closed sessions.
- Personalize messages with customer name where possible.
- Use tags to keep audiences clean.
- Review failures after every campaign.
- Monitor quality rating regularly.
- Keep catalogue PDFs updated.
- Test templates before bulk sending.

## 45. Campaign Best Practices

Before sending a campaign:

1. Confirm template is approved.
2. Confirm audience is correct.
3. Load recipients.
4. Check total recipients.
5. Send test message to internal number.
6. Confirm document/image header works.
7. Check Meta daily limit.
8. Schedule at a reasonable time.
9. Monitor failures after sending.

## 46. Bot Flow Best Practices

- Keep flows simple.
- Always add an exit or handover to human agent.
- Use clear button labels.
- Use URL buttons for web/shop links and product messages for Meta catalog products.
- Keep quick replies to 3 options and list menus to 10 rows.
- Save important customer replies into variables.
- Create CRM leads only when intent is clear.
- Test every route before activating.
- Use execution logs to debug.
- Avoid sending too many automated messages in a row.
- Use AI flow review as a checklist, not as automatic activation.

# PART K: Training Team Section

## 47. Training Goal

By the end of training, users should be able to:

- Open Team Inbox and reply to customers.
- Send templates and documents correctly.
- Understand session open vs session closed.
- Create and send a campaign.
- Use A/B Testing.
- Read message statuses.
- Link chats with CRM leads/customers.
- Understand how bot flows work.
- Know what to check when messages fail.

## 48. Trainer Preparation Checklist

Before training:

- Confirm Odoo login works.
- Confirm WhatsApp account is connected.
- Confirm at least one approved template exists.
- Confirm one document-header template exists with PDF.
- Confirm test customer/contact exists.
- Confirm Team Inbox has sample chats.
- Confirm campaign screen opens.
- Confirm Flow Builder opens.
- Confirm CRM lead creation works.
- Confirm Meta account is not over daily limit.
- Confirm commerce Catalog ID and product retailer IDs if catalogue/product demos are planned.
- Confirm AI provider test passes if AI draft demos are planned.
- Prepare one internal WhatsApp number for live testing.

## 49. Suggested Training Agenda

### Session 1: Basic Navigation

1. Show WhatsApp Marketing menu.
2. Explain Engage, Campaigns, Automation, Analytics, Compliance, Configuration.
3. Open Team Inbox.
4. Explain chat list, filters, message area, right profile panel.

### Session 2: Daily Chat Handling

1. Open a customer chat.
2. Reply with normal text.
3. Send approved template.
4. Send document-header template.
5. Assign chat to agent.
6. Add label.
7. Create opportunity.
8. Resolve chat.

### Session 3: Campaign Sending

1. Create new campaign.
2. Select account.
3. Select target type.
4. Load recipients.
5. Configure Message tab.
6. Explain A/B Testing tab.
7. Schedule/send.
8. Review sent/delivered/read/failed.

### Session 4: Templates

1. Open My Templates.
2. Explain approved vs draft.
3. Show body variables.
4. Show sample values.
5. Show document header requirement.
6. Explain preview.
7. Explain common errors.

### Session 5: Flow Builder

1. Open Flow Builder.
2. Explain trigger.
3. Show visual builder.
4. Open Steps List.
5. Configure Send Text.
6. Configure Buttons, URL Button, and Catalogue/Product steps.
7. Configure Wait Response.
8. Configure Condition.
9. Configure Assign Agent/Create Lead.
10. Run AI flow review if enabled.
11. Test flow and review logs.

### Session 6: AI and Placeholders

1. Open Placeholder Guide.
2. Show common placeholders and sample values.
3. Open AI Providers.
4. Explain provider type, base URL, API key, model, timeout, retries, and Test Provider.
5. Explain draft-only behavior.
6. Generate an AI reply draft in Team Inbox.
7. Generate a campaign draft and review spam-risk warning.

## 50. Trainer Demo Script

Use this example demo:

1. "A new customer asks for FiberaFRP catalogue."
2. Open Team Inbox.
3. Reply with greeting.
4. Send catalogue template with PDF document header.
5. Add label: `Catalogue Sent`.
6. Customer replies: "Need price."
7. Create CRM opportunity.
8. Assign to sales agent.
9. Send follow-up template.
10. Resolve the chat after handover.

Campaign demo:

1. Create campaign: `FiberaFRP Catalogue Broadcast`.
2. Target: tag `Dealer Lead`.
3. Load recipients.
4. Use approved catalogue template.
5. Send to small test audience.
6. Review statuses.

Flow demo:

1. Customer sends `support`.
2. Bot sends menu:
   - Order Issue
   - Payment Problem
   - Technical Support
   - Talk to Agent
3. Customer selects option.
4. Flow creates label or lead.
5. Flow assigns agent.

## 51. Common User Mistakes to Explain

| Mistake | Explanation |
|---|---|
| Typing normal message in closed session | WhatsApp requires template after 24-hour window. |
| Sending document template without PDF | Document-header templates require actual document media. |
| Forgetting Load Recipients | Campaign will have no recipients. |
| Using draft template | Only approved templates can send. |
| Wrong phone number format | Use country code and no spaces. |
| Ignoring failed messages | Failures show configuration or Meta issues. |
| Not checking preview | Customers may receive incomplete-looking messages. |
| Not using tags | Future targeting becomes difficult. |
| Creating too many bot steps | Users get confused; keep flow simple. |
| Putting raw catalogue IDs in the wrong field | Product messages require Catalog ID and Product Retailer ID in the commerce fields. |
| Trusting AI output without review | AI is draft-only and can be wrong. Users must review before sending or applying. |

## 52. Post-Training Verification Checklist

Ask each trainee to complete:

- Open Team Inbox.
- Search a customer chat.
- Send a normal reply.
- Send an approved template.
- Explain session closed behavior.
- Add a label to a chat.
- Create a CRM opportunity from a chat.
- Create a test campaign.
- Load recipients.
- Explain Message vs A/B Testing.
- Open a template and explain variables.
- Open a bot flow and explain one step.
- Configure one URL button or catalogue/product step.
- Open Placeholder Guide and explain one placeholder.
- Explain AI draft-only behavior.
- Read message status: sent, delivered, read, failed.

## 53. Support Escalation Checklist

When reporting an issue to the technical team, include:

- Customer phone number.
- WhatsApp account used.
- Message/template name.
- Screenshot of error.
- Time of sending.
- Campaign name if campaign-related.
- Whether message was text, media, or template.
- Whether template had document/image/video header.
- Whether message used URL button, catalogue, single product, or product list.
- Message status.
- Any failed error text.
- Whether inbound/delivered/read webhook updated.
- AI job ID or provider test status if the issue is AI-related.

## 54. Quick Reference

| Task | Menu |
|---|---|
| Reply to customer | WhatsApp Marketing > Engage > Team Inbox |
| See all messages | WhatsApp Marketing > Engage > All Messages |
| Create campaign | WhatsApp Marketing > Campaigns > All Campaigns |
| Manage audience | WhatsApp Marketing > Campaigns > Audience Segments |
| Manage templates | WhatsApp Marketing > Campaigns > My Templates |
| Open Meta template manager | WhatsApp Marketing > Campaigns > Create Template (Meta) |
| Build automation | WhatsApp Marketing > Automation > Flow Builder |
| Manage quick replies | WhatsApp Marketing > Automation > Quick Replies |
| View analytics | WhatsApp Marketing > Analytics > Dashboard |
| Manage media | WhatsApp Marketing > Analytics > Media Library |
| Manage consent | WhatsApp Marketing > Compliance > Consent Log |
| Configure account | WhatsApp Marketing > Configuration > WhatsApp Accounts |
| Configure catalogue/shop defaults | WhatsApp Marketing > Configuration > Commerce / Shop Setup |
| Configure Tally bridge | Invoicing > Configuration > Settings > Tally Integration |
| Review Tally sync logs | Invoicing > Review > Logs > Tally Sync Logs |
| Secret Apps access | `https://fibera.elsxglobal.com/elsx-secret/apps/<secret-token>` |
| See placeholders | WhatsApp Marketing > Configuration > Placeholder Guide |
| Configure AI providers | WhatsApp Marketing > Configuration > AI Providers |
| Configure AI prompts | WhatsApp Marketing > Configuration > AI Prompts |
| Review AI jobs | WhatsApp Marketing > Configuration > AI Jobs |
| Manage AI tools | WhatsApp Marketing > Configuration > AI Tools |
| Configure team | WhatsApp Marketing > Configuration > Team Setup |
| Check webhook logs | WhatsApp Marketing > Configuration > Webhook Logs |
| Global settings | WhatsApp Marketing > Configuration > Settings |

## 55. Forms, Payments, Catalogues, AI, and Dashboard Sync

### 55.1 Forms

Use **WhatsApp Marketing > Campaigns > Forms / Webviews** or **Automation > Forms / Webviews** to collect structured customer details.

Recommended form fields:

| Field | Use |
|---|---|
| Name | Customer/contact name. |
| Phone | WhatsApp/contact phone. |
| City | Delivery or project city. |
| Requirement | Product, quantity, size, load rating, and notes. |
| File Upload | Drawings, photos, purchase orders, or requirements. |
| Location | Site or delivery location. |
| Consent Checkbox | Customer consent for follow-up. |

Each field can optionally map to CRM values. Submissions are saved first; users can then create a lead or update the contact after review.

### 55.2 Payment Links

Payment links can come from:

- Manual payment URL configured on the WhatsApp account.
- Latest unpaid invoice.
- Latest quotation/order.
- Selected invoice from Team Inbox.
- Selected quotation/order from Team Inbox.

In Flow Builder, choose **Payment Source**:

| Source | Use |
|---|---|
| Account Default | Uses the WhatsApp account payment-link mode. |
| Latest Unpaid Invoice | Finds the customer's latest posted unpaid invoice. |
| Latest Quotation / Order | Finds the customer's latest quotation/order. |
| Manual URL From Account | Uses the account's manual payment URL. |

If the 24-hour WhatsApp session is closed, use an approved payment or utility template instead of a normal payment-link shortcut.

### 55.3 Catalogues and Product Messages

Configure catalogue details on **WhatsApp Account > Commerce / Shop**:

| Field | Meaning |
|---|---|
| Meta Catalog ID | Commerce Manager catalog connected to WhatsApp. |
| Default Product Retailer ID | Default product/content ID. |
| Shop / Catalogue URL | Public shop or catalogue link for URL buttons. |
| Commerce Manager URL | Admin link for maintaining products. |

Flow Builder can send:

- Full catalog/shop message.
- Single product card.
- Multi-product list.
- URL CTA button.

### 55.4 Flow Builder Parity

The embedded builder and full-screen visual builder should now support the same practical nodes:

- Text
- Template
- Buttons
- List
- Media
- Ask Question
- Wait Reply
- Condition
- Assign Agent
- Assign Team
- Add Tag
- Create Lead
- Chat Status
- Update Contact
- Set Variable
- URL Button
- Catalog / Product
- Form Link
- Payment Link
- API Call
- Delay
- End

Always reopen a saved flow once after major edits and check **Flow Health Warnings** before activating.

### 55.5 AI Drafts

AI is draft-only by default.

Admins can configure:

- Provider
- Model
- API base URL
- API key
- Response path
- Timeout and retries
- Tone and brand name per WhatsApp account
- Reply instructions and blocked behavior

AI can suggest replies, tags, next actions, and inactive flow drafts. A user must still apply the draft, send the message, or activate the flow manually.

### 55.6 Dashboard Sync

The Analytics Dashboard now combines:

- Live message and account health counts.
- Cached heavy charts.
- Form submissions and lead creation.
- Payment-link actions.
- Campaign reply rules.
- Click-to-WhatsApp source tracking.
- AI job health.
- Flow health warnings.

Use the sync badge to check whether the dashboard is **Live**, **Cached**, **Refreshing**, **Stale**, or **Error**.

## 56. Detailed Step-by-Step Operating Manual

This section is the practical day-to-day manual for users and admins. It explains what each major button means, when to use it, and what to check before clicking it.

### 56.1 First-Time Admin Setup

1. Open **WhatsApp Marketing > Configuration > WhatsApp Accounts**.
2. Click **New** to add a WhatsApp API number.
3. Fill **Account Name**, **Phone Number**, **Phone Number ID**, **Business Account / WABA ID**, **Access Token**, **API Version**, **Webhook Verify Token**, and **App Secret**.
4. Click **Test Connection**.
5. Click **Sync Meta Health**.
6. Click **Sync Templates** after Meta templates exist.
7. Open **Commerce / Shop** tab or **Configuration > Commerce / Shop Setup**.
8. Fill **Meta Catalog ID**, **Default Product Retailer ID**, **Shop / Catalogue URL**, **Commerce Manager URL**, **Default WhatsApp Form**, and **Payment Link Mode**.
9. Open **Invoicing > Configuration > Settings > Tally Integration** if invoices must connect to Tally.
10. Keep the normal **Apps** menu hidden. Use the secret Apps URL only for technical maintenance.
11. Open **Configuration > Settings** and confirm AI auto-send and AI auto-write are off.

### 56.2 Account Buttons

| Button | Purpose | When To Use |
|---|---|---|
| Test Connection | Checks Meta API credentials. | After adding/editing token or phone ID. |
| Sync Meta Health | Pulls quality rating, limits, and account health. | Before campaigns and demos. |
| Perform Meta Test Calls | Runs deeper API checks. | Admin troubleshooting. |
| Test Sidecar | Checks optional realtime socket sidecar. | Only if socket mode is enabled. |
| Sync Templates | Imports templates from Meta. | After Meta template approval. |
| Open Full Account Setup | Opens full API setup from commerce page. | When you are editing catalog/shop but need API fields. |

### 56.3 Team Inbox Buttons

| Button / Icon | Meaning | Use Case |
|---|---|---|
| Template | Send approved Meta template. | Closed session, invoice, utility, marketing follow-up. |
| Send | Send typed message or selected draft. | Open 24-hour session. |
| Attachment / Paperclip | Attach media or document. | PDF, image, product sheet, invoice, drawing. |
| AI Bulb | Generate AI draft guidance. | Suggested reply, intent, tags, next action. |
| Document / Shortcut | Open action shortcuts. | Send form, payment link, catalog, start flow. |
| Use Draft | Copy AI draft into composer. | After reviewing suggestion. |
| Regenerate | Ask AI for a new suggestion. | Draft is generic or wrong tone. |
| Start Flow | Start suggested flow manually. | Agent wants automation to continue. |
| Clear | Remove AI guidance panel. | Clean composer. |
| View Partner | Open contact. | Check phone, email, tags, invoices, sales history. |
| Opportunity | Create/open CRM lead. | Price, catalogue, dealer, quotation enquiry. |
| Quote | Create quotation. | Customer is ready for pricing. |
| Send Form Link | Send selected/default WhatsApp form URL. | Collect structured details. |
| Send Payment Link | Send invoice/quotation/manual payment link. | Customer asks how to pay. |

Important rule: normal text works only when the WhatsApp session is open. If the session is closed, use **Template**.

### 56.4 Team Inbox Example

Scenario: customer asks for price.

1. Open **Team Inbox**.
2. Search/open the customer chat.
3. Check name, phone, assigned agent, opportunity, orders, and invoices in the right panel.
4. If the session is open, reply:

```text
Hi {{name}}, thanks for your enquiry. Please share product type, size, quantity, and delivery city so we can quote accurately.
```

5. Click **Opportunity** to create CRM lead.
6. Click **Send Form Link** and choose **Quote Request** if more details are needed.
7. Add tag such as `Quote Requested`.
8. Assign the chat to sales.
9. Resolve the chat only after handoff or response is complete.

### 56.5 Template Workflow

1. Open **Campaigns > My Templates**.
2. Open a template.
3. Check status, category, language code, variables, samples, header media, and buttons.
4. Review the full preview.
5. Send a test to an internal number before campaign use.

| Button Type | Purpose | Example |
|---|---|---|
| Quick Reply | Customer taps a reply. | Catalogue, Price, Support |
| URL CTA | Opens website, payment, catalogue, shop. | Open Catalogue |
| Phone CTA | Starts phone call. | Call Sales |
| Copy Code | OTP/auth code use only. | Copy OTP |
| Catalog/Product | Opens Meta commerce product/catalog. | View Product |

### 56.6 Campaign Workflow

1. Open **Campaigns > All Campaigns**.
2. Click **New**.
3. Fill campaign name and WhatsApp account.
4. Select target type and approved template.
5. Click **Load Recipients**.
6. Review recipients, invalid numbers, opt-out exclusions, template media, daily limit, quiet hours, and reply rules.
7. Send a test first.
8. Schedule or send.
9. Watch status and failures.

| Campaign Button | Purpose |
|---|---|
| Load Recipients | Builds final send list from selected audience. |
| Sync Template Buttons | Creates reply rules from template quick replies. |
| Readiness Checklist | Shows recipients, media, DND, reply rules, forms, payments, tracking. |
| Draft Content | Uses AI to suggest copy; user must review. |
| Export Failed | Downloads failed recipients. |
| Replay Failed | Safely requeues selected failures. |
| Determine Winner | Picks A/B winner after enough data. |

### 56.7 Forms Workflow

Production form templates include:

- Lead Enquiry
- Support Ticket
- Catalogue Request
- Quote Request
- Feedback

Use forms when free-text chat would be messy.

1. Open **Campaigns > Forms / Webviews** or **Automation > Forms / Webviews**.
2. Open a form.
3. Review fields and required flags.
4. Confirm consent checkbox for campaign/lead forms.
5. Send the public form link from Inbox or Flow Builder.
6. Review submissions.
7. Create/update lead or contact manually unless auto-create is intentionally enabled.

| Field Type | Purpose |
|---|---|
| Short Text | Name, company, reference number. |
| Long Text | Requirement or issue details. |
| Phone | WhatsApp/contact number. |
| Email | Optional email. |
| Number | Quantity, rating, amount. |
| Dropdown | Product type, issue type, rating. |
| File Upload | Drawing, photo, BOQ, invoice, proof. |
| Location | Site or delivery location. |
| Consent Checkbox | Permission to contact customer. |

### 56.8 Flow Builder Workflow

1. Open **Automation > Flow Builder**.
2. Open a blueprint flow.
3. Read the description.
4. Review **Flow Health Warnings**.
5. Open each step and check action type, message, form, payment source, catalog IDs, assigned user/team, and next routes.
6. Click **Test Flow**.
7. Activate only after successful testing.

| Step Type | What It Does | Example |
|---|---|---|
| Send Text | Sends bot message. | Welcome or confirmation. |
| Send Template | Sends approved Meta template. | Closed-session reminder. |
| Send Media | Sends PDF/image/video. | Catalogue PDF. |
| Send Buttons | Shows up to 3 quick replies. | Price, Catalogue, Support. |
| Send List Menu | Shows up to 10 row options. | Full business menu. |
| Send URL Button | Sends one CTA URL button. | Open Catalogue. |
| Send Catalog / Product | Sends Meta catalog/product. | Single product card. |
| Send Form Link | Sends public form URL. | Quote Request form. |
| Send Payment Link | Sends invoice/quote/manual payment link. | Pay invoice. |
| Ask / Collect Input | Asks question and saves reply. | Quantity, city, order number. |
| Wait for Response | Pauses until customer replies. | Free-text requirement. |
| Condition | Routes based on reply/variable. | If reply contains price. |
| Transfer to Agent | Assigns a user. | Sales/support handoff. |
| Assign Team | Assigns from team pool. | Least busy support agent. |
| Create Lead | Creates CRM opportunity. | Quote enquiry. |
| Assign Tag | Adds contact tag. | Catalogue Requested. |
| Update Chat Status | Opens/resolves/snoozes chat. | Mark resolved after flow. |
| Update Contact Attribute | Saves customer value. | City or product interest. |
| HTTP Request | Calls external API. | Order status lookup. |
| Set Variable | Stores fixed flow value. | Source = WhatsApp Bot. |
| Delay | Waits before next step. | Follow-up after 10 minutes. |
| End | Stops automation. | Conversation handed off. |

### 56.9 Advanced Business Flow Blueprints

The system includes inactive blueprints. They do not run until an admin activates them.

#### FiberaFRP Full Business Assistant - Blueprint

Purpose: one main menu for most inbound customer journeys.

| Customer Option | What Happens |
|---|---|
| Catalogue / Shop | Sends catalogue/shop URL and tags catalogue interest. |
| New Quote | Sends quote request form and creates CRM lead. |
| Order / Payment | Offers payment link or order/accounts handoff. |
| Support / Warranty | Sends support ticket form and assigns support. |
| Dealer / Project | Sends lead enquiry form and tags project/dealer lead. |
| Talk to Agent | Assigns human agent. |

Trigger keywords:

```text
menu, business, fibera, hi, hello, start
```

#### FiberaFRP Quote Qualification - Blueprint

Purpose: collect enough data for accurate pricing.

Steps:

1. Greet customer.
2. Ask product type.
3. Ask size/load rating.
4. Ask quantity.
5. Ask delivery city.
6. Create CRM lead.
7. Send Quote Request form.
8. Assign sales agent.
9. End.

Example:

```text
Customer: price
Bot: Which product do you need?
Customer: FRP manhole cover
Bot: Please share size and load rating.
Customer: 600x600, heavy duty
Bot: How many pieces?
Customer: 40
Bot: Which city?
Customer: Ahmedabad
Bot: Lead created, form sent, sales assigned.
```

#### FiberaFRP Support And Warranty Desk - Blueprint

Purpose: route support without losing details.

Options:

- Order Status
- Payment / Invoice
- Product Issue
- Warranty / Replacement
- Talk to Agent

The flow asks for reference, issue details, sends support form, tags support, assigns an agent, and confirms handoff.

#### FiberaFRP Payment And Order Follow-Up - Blueprint

Purpose: handle payment, invoice, and order follow-up.

Options:

- Pay Now
- Order Status
- Invoice Help

The flow sends payment link if available, collects reference number, tags payment follow-up, and assigns accounts/order support.

#### FiberaFRP Feedback And Review - Blueprint

Purpose: capture post-sale feedback.

Options:

- Good
- Average
- Poor

The flow sends feedback form, tags feedback received, and keeps the result reviewable.

### 56.10 Before Activating Any Flow

- Account is connected.
- Webhook is fresh.
- Flow has no health warnings.
- Every button/list option has a route.
- No self-loop exists.
- Forms are active and have fields.
- Payment links are enabled if payment steps exist.
- Catalog ID/product IDs are filled if catalog steps exist.
- Human handoff user/team is valid.
- Test number receives expected messages.
- CRM lead creation is checked.
- AI auto-send is off.

### 56.11 Client Demo Checklist

1. Open Dashboard and confirm sync state.
2. Open WhatsApp Account and confirm status connected.
3. Open Commerce / Shop Setup and confirm catalog/shop/payment defaults.
4. Open Team Inbox and switch chats.
5. Send or preview one template.
6. Open Forms and show Lead Enquiry / Quote Request / Support Ticket.
7. Open Flow Builder and show inactive business blueprints.
8. Run one test flow with internal test number.
9. Open Campaigns and show readiness checklist.
10. Open AI Providers and show draft-only settings.
11. Open Diagnostics and review warnings.

# End of Guide
