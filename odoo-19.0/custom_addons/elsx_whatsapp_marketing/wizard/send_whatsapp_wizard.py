# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhatsAppSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message Wizard'

    @api.model
    def _default_account_id(self):
        return self.env['whatsapp.account'].search([('active', '=', True)], limit=1)

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, default=_default_account_id)
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    phone_number = fields.Char(
        'Direct Phone Number',
        help='Send to a number not in contacts (include country code, e.g. 917247558873)'
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string='Template',
        domain="[('account_id', '=', account_id), ('status', '=', 'approved')]",
    )
    media_file = fields.Binary('Media / Voice File')
    media_filename = fields.Char('Media Filename')
    message_body = fields.Text('Message', help="Leave empty to use template body or send media without a caption")
    template_preview_html = fields.Html(
        string='Template Live Preview',
        compute='_compute_template_preview_html',
    )

    @api.depends('template_id')
    def _compute_template_preview_html(self):
        for record in self:
            if not record.template_id:
                record.template_preview_html = False
                continue
            
            t = record.template_id
            
            # Header
            header_html = ""
            if t.header_type == 'text' and t.header_text:
                header_html = f'<div style="font-weight: bold; font-size: 0.95rem; color: #111B21; margin-bottom: 4px;">{t.header_text}</div>'
            elif t.header_type == 'image':
                header_html = '<div style="background: #E9EDEF; border-radius: 6px; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 8px; color: #667781;"><i class="fa fa-image fa-2x" title="Header Image"></i></div>'
            elif t.header_type == 'video':
                header_html = '<div style="background: #E9EDEF; border-radius: 6px; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 8px; color: #667781;"><i class="fa fa-video-camera fa-2x" title="Header Video"></i></div>'
            elif t.header_type == 'document':
                header_html = '<div style="background: #E9EDEF; border-radius: 6px; height: 60px; display: flex; align-items: center; justify-content: center; margin-bottom: 8px; color: #667781;"><i class="fa fa-file-pdf-o fa-lg me-2" title="Header Document"></i><span>Document Preview</span></div>'

            # Body (replace variables with beautiful highlighting, e.g. {{1}} -> [Var 1])
            body_text = t.body or ""
            # Escape HTML in body
            body_text = body_text.replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br/>")
            # Highlight placeholders like {{1}}, {{2}} in vibrant modern badges
            body_text = re.sub(
                r'\\{\\{(\d+)\\}\\}', 
                r'<span class="badge rounded-pill bg-light text-primary border px-2 py-1 mx-1" style="font-weight: 500;">[Var \g<1>]</span>', 
                body_text
            )

            # Footer
            footer_html = ""
            if t.footer:
                footer_html = f'<div style="font-size: 0.75rem; color: #667781; margin-top: 6px;">{t.footer}</div>'

            # Buttons
            buttons_html = ""
            if t.has_buttons:
                buttons_list = []
                if t.button_type == 'quick_reply':
                    if t.button_text_1: buttons_list.append(t.button_text_1)
                    if t.button_text_2: buttons_list.append(t.button_text_2)
                    if t.button_text_3: buttons_list.append(t.button_text_3)
                elif t.button_type == 'call_to_action':
                    if t.cta_url_text: buttons_list.append(f'<i class="fa fa-external-link me-1"></i>{t.cta_url_text}')
                    if t.cta_phone_text: buttons_list.append(f'<i class="fa fa-phone me-1"></i>{t.cta_phone_text}')
                elif t.button_type == 'copy_code':
                    buttons_list.append('<i class="fa fa-copy me-1"></i>Copy Code')

                if buttons_list:
                    btn_elements = []
                    for btn in buttons_list:
                        btn_elements.append(f'''
                            <div style="background: #FFFFFF; color: #00A884; font-weight: 600; text-align: center; padding: 10px; font-size: 0.85rem; border-top: 1px solid #E9EDEF; cursor: pointer; flex: 1 1 auto; display: flex; align-items: center; justify-content: center;">
                                {btn}
                            </div>
                        ''')
                    
                    buttons_html = f'<div style="display: flex; flex-direction: column; margin-top: 8px; border-radius: 0 0 8px 8px; overflow: hidden;">{"".join(btn_elements)}</div>'

            # Combine into a premium, hyper-realistic WhatsApp chat bubble!
            record.template_preview_html = f'''
                <div class="d-flex justify-content-start align-items-end p-3 rounded" style="background: #efeae2; background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png'); background-repeat: repeat; background-size: 200px; min-height: 200px;">
                    <div style="background: #FFFFFF; border-radius: 8px; box-shadow: 0 1px 0.5px rgba(11,20,26,.13); max-width: 85%; width: 100%; position: relative; border-top-left-radius: 0;">
                        <!-- WhatsApp bubble tail -->
                        <div style="position: absolute; left: -8px; top: 0; width: 0; height: 0; border-top: 8px solid #FFFFFF; border-left: 8px solid transparent;"></div>
                        
                        <!-- Content container -->
                        <div style="padding: 8px 10px 8px 12px;">
                            {header_html}
                            <div style="font-size: 0.9rem; line-height: 1.4; color: #111B21; white-space: pre-wrap; word-wrap: break-word;">{body_text}</div>
                            {footer_html}
                            <div style="font-size: 0.65rem; color: #667781; text-align: right; margin-top: 2px;">
                                {fields.Datetime.now().strftime('%I:%M %p')}
                            </div>
                        </div>
                        {buttons_html}
                    </div>
                </div>
            '''

    def _normalize_phone(self, phone):
        """Normalize and validate recipient numbers before calling Meta."""
        return self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id, strict=True)

    def _detect_media_type(self):
        filename = (self.media_filename or '').lower()
        if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            return 'image'
        if filename.endswith(('.mp4', '.mov', '.avi', '.3gp')):
            return 'video'
        if filename.endswith(('.mp3', '.ogg', '.wav', '.aac', '.m4a', '.opus')):
            return 'audio'
        return 'document'

    def _send_to_recipient(self, phone, partner=False):
        partner_id = partner.id if partner else False
        if self.template_id:
            self.account_id.send_message(
                to_number=phone,
                message_type='template',
                template_record=self.template_id,
                partner_id=partner_id,
            )
            return

        if self.media_file:
            media_type = self._detect_media_type()
            message = self.env['whatsapp.message'].create({
                'account_id': self.account_id.id,
                'phone_number': phone,
                'partner_id': partner_id,
                'message_type': media_type,
                'body': self.message_body or False,
                'caption': self.message_body if media_type in ('image', 'video', 'document') else False,
                'media_file': self.media_file,
                'media_filename': self.media_filename or 'attachment',
                'direction': 'outbound',
            })
            message.action_send()
            return

        self.account_id.send_message(
            to_number=phone,
            message_type='text',
            body=self.message_body,
            partner_id=partner_id,
        )

    def action_send(self):
        """Send WhatsApp message to selected partners or direct phone number"""
        self.ensure_one()
        sent_count = 0
        errors = []

        if not self.partner_ids and not self.phone_number:
            raise UserError(_('Please select at least one recipient or enter a Direct Phone Number.'))

        # Send to direct phone number if provided
        if self.phone_number:
            phone = self._normalize_phone(self.phone_number)
            try:
                self._send_to_recipient(phone)
                sent_count += 1
            except Exception as e:
                errors.append(f"{phone}: {str(e)}")

        # Send to each partner
        for partner in self.partner_ids:
            # Odoo 19 uses 'phone'; older versions had 'mobile' — handle gracefully
            phone = getattr(partner, 'mobile', None) or getattr(partner, 'phone', None)
            if not phone:
                errors.append(f"{partner.name}: No phone number on record")
                continue
            phone = self._normalize_phone(phone)
            try:
                self._send_to_recipient(phone, partner=partner)
                sent_count += 1
            except Exception as e:
                errors.append(f"{partner.name}: {str(e)}")

        if errors and not sent_count:
            raise UserError(_("All messages failed to send:\n%s") % "\n".join(errors))

        msg = f'WhatsApp messages sent to {sent_count} recipient(s).'
        if errors:
            msg += '\n\nWarnings:\n' + '\n'.join(errors)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Done' if not errors else 'Sent with Warnings',
                'message': msg,
                'type': 'success' if not errors else 'warning',
                'sticky': bool(errors),
            }
        }
