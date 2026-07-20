# -*- coding: utf-8 -*-
from odoo import models, fields, api
import re
import logging
from html import escape as html_escape

_logger = logging.getLogger(__name__)


class WhatsAppSampleTemplate(models.Model):
    """Pre-built template library - ready-to-import enterprise-grade templates"""
    _name = 'whatsapp.sample.template'
    _description = 'WhatsApp Sample Template Library'
    _order = 'industry, category, name'

    name = fields.Char('Template Name', required=True)
    display_name_clean = fields.Char('Template Title', compute='_compute_display_name_clean', store=True)

    industry = fields.Selection([
        ('general', 'General'),
        ('ecommerce', 'E-Commerce & Retail'),
        ('finance', 'Finance & Banking'),
        ('healthcare', 'Healthcare'),
        ('realestate', 'Real Estate'),
        ('education', 'Education'),
        ('travel', 'Travel & Hospitality'),
        ('food', 'Food & Restaurant'),
        ('automotive', 'Automotive'),
        ('saas', 'SaaS & Technology'),
    ], string='Industry', default='general', required=True)

    category = fields.Selection([
        ('marketing', 'Marketing'),
        ('utility', 'Utility'),
        ('authentication', 'Authentication'),
    ], string='Category', default='marketing', required=True)

    # Content
    header_type = fields.Selection([
        ('none', 'None'),
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
    ], string='Header Type', default='none')
    header_text = fields.Char('Header Text')

    body = fields.Text('Body', required=True)
    footer = fields.Char('Footer')

    # Buttons
    has_buttons = fields.Boolean('Has Buttons', default=False)
    button_type = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('call_to_action', 'Call to Action'),
    ], string='Button Type')
    button_text_1 = fields.Char('Button 1')
    button_text_2 = fields.Char('Button 2')
    button_text_3 = fields.Char('Button 3')
    cta_url_text = fields.Char('URL Button Text')
    cta_url_link = fields.Char('URL Link')
    cta_phone_text = fields.Char('Phone Button Text')
    cta_phone_number = fields.Char('Phone Number')

    # Metadata
    variable_count = fields.Integer('Variables', compute='_compute_variable_count', store=True)
    language = fields.Selection([
        ('en', 'English'),
        ('en_US', 'English (US)'),
        ('hi', 'Hindi'),
    ], string='Language', default='en')
    is_imported = fields.Boolean('Already Imported', default=False, copy=False)
    description = fields.Text('Description', help='Brief explanation of when to use this template')
    color = fields.Integer('Color Index', default=0)

    # Preview
    preview_html = fields.Html('Preview', compute='_compute_preview_html', sanitize=False)
    preview_text = fields.Text('Preview Text', compute='_compute_preview_html')

    @api.depends('name')
    def _compute_display_name_clean(self):
        for rec in self:
            rec.display_name_clean = (rec.name or '').replace('_', ' ').title()

    @api.depends('body')
    def _compute_variable_count(self):
        for rec in self:
            rec.variable_count = len(re.findall(r'\{\{\d+\}\}', rec.body or ''))

    @api.depends('body', 'header_type', 'header_text', 'footer', 'has_buttons',
                 'button_text_1', 'button_text_2', 'button_text_3', 'category')
    def _compute_preview_html(self):
        for rec in self:
            header_html = ""
            text_lines = []
            if rec.header_type == 'text' and rec.header_text:
                header_html = f"<div style='font-weight:700;margin-bottom:4px;color:#111b21;font-size:14px;'>{html_escape(rec.header_text)}</div>"
                text_lines.append("Header: %s" % rec.header_text)
            elif rec.header_type in ('image', 'video'):
                icon = 'image' if rec.header_type == 'image' else 'play-circle'
                header_html = f"<div style='background:#e9edef;height:100px;border-radius:6px;margin-bottom:6px;display:flex;align-items:center;justify-content:center;'><i class='fa fa-{icon} fa-2x' style='color:#8696a0;'></i></div>"
                text_lines.append("Header: %s placeholder" % rec.header_type.title())

            body_html = f"<div style='color:#111b21;font-size:13px;white-space:pre-wrap;line-height:1.4;'>{html_escape(rec.body or '')}</div>"
            text_lines.append(rec.body or '')

            footer_html = ""
            if rec.footer:
                footer_html = f"<div style='color:#667781;font-size:11px;margin-top:4px;'>{html_escape(rec.footer)}</div>"
                text_lines.append("Footer: %s" % rec.footer)

            buttons_html = ""
            button_labels = []
            if rec.has_buttons:
                for btn in [rec.button_text_1, rec.button_text_2, rec.button_text_3]:
                    if btn:
                        button_labels.append(btn)
                        buttons_html += f"""
                        <div style="background: #fff; border-radius: 8px; padding: 10px; text-align: center; color: #008069; font-weight: 600; font-size: 13px; margin-top: 4px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); cursor: pointer; transition: background 0.2s;">
                            {html_escape(btn)}
                        </div>"""
            if button_labels:
                text_lines.append("Buttons: %s" % " | ".join(button_labels))

            rec.preview_html = f"""
            <div class="o_whatsapp_preview_container" style="max-width:320px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                <div class="o_whatsapp_preview_chat_bg" style="background-color: #efeae2; background-image: radial-gradient(rgba(17,27,33,.06) .8px, transparent .8px); background-size: 18px 18px; padding: 20px; border-radius: 16px; box-shadow: inset 0 0 20px rgba(0,0,0,0.05); min-height: 200px;">
                    <div class="o_whatsapp_bubble" style="background: #d9fdd3; border-radius: 8px 8px 0 8px; padding: 10px 12px; position: relative; box-shadow: 0 1px 0.5px rgba(11,20,26,.13); margin-left: auto; width: fit-content; max-width: 90%;">
                        {header_html}
                        {body_html}
                        {footer_html}
                        <div style="display: flex; justify-content: flex-end; align-items: center; gap: 4px; margin-top: 4px;">
                            <span style="font-size: 11px; color: #667781;">10:42 AM</span>
                            <span style="color: #53bdeb; font-size: 11px; line-height: 1;">read</span>
                        </div>
                    </div>
                    <div style="width: 90%; margin-left: auto;">
                        {buttons_html}
                    </div>
                </div>
            </div>
            """
            rec.preview_text = "\n".join(line for line in text_lines if line)

    def action_import_to_templates(self):
        """Import this sample template into the user's template library"""
        self.ensure_one()
        Template = self.env['whatsapp.template']

        account = self.env['whatsapp.account']._get_default_account()

        vals = {
            'name': self.name,
            'category': self.category,
            'language': self.language or 'en',
            'language_code': self.language or 'en',
            'header_type': self.header_type or 'none',
            'header_text': self.header_text,
            'body': self.body,
            'footer': self.footer,
            'has_buttons': self.has_buttons,
            'button_type': self.button_type,
            'button_text_1': self.button_text_1,
            'button_text_2': self.button_text_2,
            'button_text_3': self.button_text_3,
            'cta_url_text': self.cta_url_text,
            'cta_url_link': self.cta_url_link,
            'cta_phone_text': self.cta_phone_text,
            'cta_phone_number': self.cta_phone_number,
            'status': 'draft',
        }
        if account:
            vals['account_id'] = account.id

        template = Template.create(vals)
        self.is_imported = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Template Imported!',
                'message': f'"{self.display_name_clean}" has been added to your templates. You can now edit and submit it to Meta.',
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'whatsapp.template',
                    'res_id': template.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            }
        }

    @api.model
    def _seed_sample_templates(self):
        """Populate the library with enterprise-grade sample templates"""
        samples = [
            # ─── E-COMMERCE ───
            {
                'name': 'order_confirmation',
                'industry': 'ecommerce',
                'category': 'utility',
                'header_type': 'text',
                'header_text': '✅ Order Confirmed!',
                'body': 'Hi {{1}},\n\nYour order *#{{2}}* has been confirmed!\n\n📦 Items: {{3}}\n💰 Total: ₹{{4}}\n🚚 Expected Delivery: {{5}}\n\nTrack your order anytime by clicking below.',
                'footer': 'Thank you for shopping with us!',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '📦 Track Order', 'cta_url_link': 'https://example.com/track/{{1}}',
                'description': 'Send after order placement. Variables: Name, Order ID, Items, Total, Delivery date.',
            },
            {
                'name': 'abandoned_cart_reminder',
                'industry': 'ecommerce',
                'category': 'marketing',
                'header_type': 'image',
                'body': 'Hey {{1}}! 👋\n\nYou left some amazing items in your cart:\n\n🛒 {{2}}\n\n💸 Complete your purchase now and get *{{3}}% OFF* with code *COMEBACK*!\n\nHurry — offer expires in 24 hours ⏰',
                'footer': 'Reply STOP to opt out',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '🛒 Complete Purchase', 'cta_url_link': 'https://example.com/cart',
                'description': 'Recover abandoned carts. Variables: Name, Cart items, Discount %.',
            },
            {
                'name': 'delivery_update',
                'industry': 'ecommerce',
                'category': 'utility',
                'body': 'Hi {{1}},\n\n🚚 Your order *#{{2}}* is *out for delivery*!\n\nDelivery Partner: {{3}}\nEstimated Time: {{4}}\n\nPlease keep your phone handy.',
                'footer': 'Need help? Reply to this message.',
                'description': 'Delivery status update. Variables: Name, Order ID, Partner, ETA.',
            },
            {
                'name': 'review_request',
                'industry': 'ecommerce',
                'category': 'marketing',
                'body': 'Hi {{1}}! 🌟\n\nWe hope you loved your recent purchase (*{{2}}*).\n\nWould you take a moment to rate your experience? Your feedback means everything to us!\n\n⭐⭐⭐⭐⭐',
                'has_buttons': True, 'button_type': 'quick_reply',
                'button_text_1': '⭐ Rate Now', 'button_text_2': '🙏 Later',
                'footer': 'Reply STOP to opt out',
                'description': 'Post-delivery review request. Variables: Name, Product name.',
            },
            # ─── FINANCE ───
            {
                'name': 'payment_reminder',
                'industry': 'finance',
                'category': 'utility',
                'header_type': 'text',
                'header_text': '⏰ Payment Reminder',
                'body': 'Dear {{1}},\n\nThis is a friendly reminder that your payment of *₹{{2}}* for invoice *{{3}}* is due on *{{4}}*.\n\nPlease make the payment at your earliest convenience to avoid late charges.',
                'footer': 'For queries, contact our finance team.',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '💳 Pay Now', 'cta_url_link': 'https://example.com/pay',
                'description': 'Payment reminder. Variables: Name, Amount, Invoice #, Due date.',
            },
            {
                'name': 'transaction_alert',
                'industry': 'finance',
                'category': 'utility',
                'body': '🔔 *Transaction Alert*\n\nDear {{1}},\n\nA {{2}} of *₹{{3}}* has been {{4}} on your account ending *{{5}}*.\n\nDate: {{6}}\nBalance: ₹{{7}}\n\nIf this wasn\'t you, call us immediately.',
                'footer': 'This is an automated alert.',
                'description': 'Transaction notification. Variables: Name, Type, Amount, Status, Account, Date, Balance.',
            },
            # ─── HEALTHCARE ───
            {
                'name': 'appointment_reminder',
                'industry': 'healthcare',
                'category': 'utility',
                'header_type': 'text',
                'header_text': '🏥 Appointment Reminder',
                'body': 'Dear {{1}},\n\nThis is a reminder for your appointment:\n\n👨‍⚕️ Doctor: Dr. {{2}}\n📅 Date: {{3}}\n🕐 Time: {{4}}\n📍 Location: {{5}}\n\nPlease arrive 15 minutes early.',
                'has_buttons': True, 'button_type': 'quick_reply',
                'button_text_1': '✅ Confirm', 'button_text_2': '🔄 Reschedule', 'button_text_3': '❌ Cancel',
                'description': 'Appointment reminder. Variables: Patient, Doctor, Date, Time, Location.',
            },
            {
                'name': 'lab_report_ready',
                'industry': 'healthcare',
                'category': 'utility',
                'body': 'Dear {{1}},\n\nYour lab report for *{{2}}* is ready.\n\n📋 Report ID: {{3}}\n📅 Test Date: {{4}}\n\nYou can download it securely using the link below.',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '📥 Download Report', 'cta_url_link': 'https://example.com/report',
                'description': 'Lab report notification. Variables: Patient, Test name, Report ID, Date.',
            },
            # ─── REAL ESTATE ───
            {
                'name': 'property_inquiry_response',
                'industry': 'realestate',
                'category': 'marketing',
                'header_type': 'image',
                'body': 'Hi {{1}}! 🏠\n\nThank you for your interest in *{{2}}*.\n\n📍 Location: {{3}}\n💰 Price: ₹{{4}}\n📐 Area: {{5}} sq.ft.\n\nWould you like to schedule a site visit?',
                'has_buttons': True, 'button_type': 'quick_reply',
                'button_text_1': '📅 Schedule Visit', 'button_text_2': '📞 Call Me', 'button_text_3': '📸 More Photos',
                'description': 'Property inquiry auto-response. Variables: Name, Property, Location, Price, Area.',
            },
            # ─── EDUCATION ───
            {
                'name': 'admission_confirmation',
                'industry': 'education',
                'category': 'utility',
                'header_type': 'text',
                'header_text': '🎓 Admission Confirmed!',
                'body': 'Dear {{1}},\n\nCongratulations! Your admission to *{{2}}* has been confirmed.\n\n📚 Course: {{3}}\n📅 Start Date: {{4}}\n💰 Fee: ₹{{5}}\n\nPlease complete the remaining formalities before the start date.',
                'footer': 'Welcome aboard!',
                'description': 'Admission confirmation. Variables: Name, Institute, Course, Start date, Fee.',
            },
            # ─── FOOD & RESTAURANT ───
            {
                'name': 'table_reservation_confirm',
                'industry': 'food',
                'category': 'utility',
                'body': 'Hi {{1}}! 🍽️\n\nYour table reservation has been confirmed:\n\n📅 Date: {{2}}\n🕐 Time: {{3}}\n👥 Guests: {{4}}\n📍 {{5}}\n\nSee you soon!',
                'has_buttons': True, 'button_type': 'quick_reply',
                'button_text_1': '✅ Confirmed', 'button_text_2': '🔄 Change',
                'description': 'Table booking confirmation. Variables: Name, Date, Time, Guests, Location.',
            },
            # ─── GENERAL / MULTI-INDUSTRY ───
            {
                'name': 'welcome_message',
                'industry': 'general',
                'category': 'marketing',
                'body': 'Hi {{1}}! 👋\n\nWelcome to *{{2}}*! We\'re thrilled to have you.\n\nHere\'s what you can do:\n✅ Browse our products\n📞 Get instant support\n🔔 Receive updates & offers\n\nHow can we help you today?',
                'has_buttons': True, 'button_type': 'quick_reply',
                'button_text_1': '🛍️ Products', 'button_text_2': '📞 Support', 'button_text_3': '💰 Offers',
                'description': 'Welcome/onboarding message. Variables: Name, Business name.',
            },
            {
                'name': 'feedback_survey',
                'industry': 'general',
                'category': 'marketing',
                'body': 'Hi {{1}}! ⭐\n\nWe value your opinion! How was your recent experience with us?\n\nPlease rate us:\n1️⃣ ⭐⭐⭐⭐⭐ Excellent\n2️⃣ ⭐⭐⭐⭐ Good\n3️⃣ ⭐⭐⭐ Average\n4️⃣ ⭐⭐ Below Average\n5️⃣ ⭐ Poor\n\nJust reply with a number!',
                'footer': 'Your feedback helps us improve.',
                'description': 'CSAT feedback survey. Variables: Name.',
            },
            {
                'name': 'otp_verification',
                'industry': 'general',
                'category': 'authentication',
                'body': 'Your verification code is *{{1}}*.\n\nThis code expires in 10 minutes. Do not share it with anyone.',
                'footer': 'If you didn\'t request this, ignore this message.',
                'description': 'OTP / Authentication code. Variables: OTP code.',
            },
            {
                'name': 'seasonal_sale_announcement',
                'industry': 'general',
                'category': 'marketing',
                'header_type': 'image',
                'body': '🔥 *MEGA SALE IS LIVE!* 🔥\n\nHi {{1}},\n\nGet up to *{{2}}% OFF* on everything!\n\n🛍️ Shop Now: {{3}}\n⏰ Ends: {{4}}\n\nDon\'t miss out — your favorites are selling fast! 🏃‍♂️',
                'footer': 'Reply STOP to opt out',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '🛒 Shop Now', 'cta_url_link': 'https://example.com/sale',
                'description': 'Seasonal promotion blast. Variables: Name, Discount %, URL, End date.',
            },
            {
                'name': 'event_invitation',
                'industry': 'general',
                'category': 'marketing',
                'header_type': 'image',
                'body': 'Hi {{1}}! 🎉\n\nYou\'re invited to *{{2}}*!\n\n📅 Date: {{3}}\n🕐 Time: {{4}}\n📍 Venue: {{5}}\n\nRegister now to confirm your spot. Limited seats available!',
                'has_buttons': True, 'button_type': 'call_to_action',
                'cta_url_text': '🎟️ Register Now', 'cta_url_link': 'https://example.com/event',
                'description': 'Event/webinar invitation. Variables: Name, Event, Date, Time, Venue.',
            },
        ]

        created = 0
        for s in samples:
            existing = self.search([('name', '=', s['name'])], limit=1)
            if not existing:
                self.create(s)
                created += 1

        return created
