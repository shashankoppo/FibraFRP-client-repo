# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhatsAppSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message Wizard'

    @api.model
    def _default_account_id(self):
        return self.env['whatsapp.account']._get_default_account()

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
    template_preview_text = fields.Text(
        string='Template Preview Text',
        compute='_compute_template_preview_html',
    )
    template_requires_header_media = fields.Boolean(
        compute='_compute_template_requires_header_media',
    )

    @api.depends('template_id', 'template_id.header_type')
    def _compute_template_requires_header_media(self):
        for record in self:
            record.template_requires_header_media = record.template_id.header_type in ('image', 'video', 'document')

    @api.depends(
        'template_id',
        'template_id.body',
        'template_id.footer',
        'template_id.header_type',
        'template_id.header_text',
        'template_id.header_media_file',
        'template_id.header_media_filename',
        'template_id.header_media_url',
        'template_id.has_buttons',
        'template_id.button_type',
        'template_id.button_text_1',
        'template_id.button_text_2',
        'template_id.button_text_3',
        'template_id.cta_url_text',
        'template_id.cta_phone_text',
        'template_id.variable_ids',
        'template_id.variable_ids.sample_value',
        'media_file',
        'media_filename',
    )
    def _compute_template_preview_html(self):
        for record in self:
            if not record.template_id:
                record.template_preview_html = False
                record.template_preview_text = False
                continue
            partner = record.partner_ids[:1]
            chat_id = record.env.context.get('default_chat_id')
            if not partner and chat_id:
                chat = record.env['whatsapp.chat'].browse(chat_id).exists()
                partner = chat.partner_id if chat else False
            record.template_preview_html = record.template_id._render_customer_preview_html(
                partner=partner,
                header_media_file=record.media_file,
                header_media_filename=record.media_filename,
                shell=True,
                compact=True,
            )
            record.template_preview_text = record.template_id._render_customer_preview_text(
                partner=partner,
                header_media_file=record.media_file,
                header_media_filename=record.media_filename,
            )

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

    def _template_header_media_filename(self):
        self.ensure_one()
        filename = self.media_filename or self.template_id.header_media_filename
        if filename and '.' in filename:
            return filename
        template_name = self.template_id._get_send_template_name() if self.template_id else 'template'
        filename = filename or f"{template_name}_header"
        extension = {
            'image': 'jpg',
            'video': 'mp4',
            'document': 'pdf',
        }.get(self.template_id.header_type if self.template_id else 'document', 'bin')
        return f"{filename}.{extension}"

    def _previous_template_header_media_kwargs(self):
        """Reuse the latest media sent with this template when the template lost its default file.

        This keeps restored/reinstalled databases usable without silently changing template
        records. If the old Meta media id has expired, the normal send path will return a
        readable Meta failure instead of blocking this wizard before send.
        """
        self.ensure_one()
        if not self.template_id:
            return {}
        previous_message = self.env['whatsapp.message'].sudo().search([
            ('account_id', '=', self.account_id.id),
            ('template_id', '=', self.template_id.id),
            ('message_type', '=', 'template'),
            ('direction', '=', 'outbound'),
            '|',
            ('media_file', '!=', False),
            ('media_url', '!=', False),
        ], order='id desc', limit=1)
        if not previous_message:
            return {}
        filename = (
            previous_message.media_filename
            or self.template_id.header_media_filename
            or self._template_header_media_filename()
        )
        if previous_message.media_file:
            return {
                'header_media_file': previous_message.media_file,
                'header_media_filename': filename,
            }
        if previous_message.media_url:
            return {
                'header_media_url': previous_message.media_url,
                'header_media_filename': filename,
            }
        return {}

    def _prepare_template_header_media_kwargs(self):
        self.ensure_one()
        if not self.template_id or self.template_id.header_type not in ('image', 'video', 'document'):
            return {}
        if self.media_file:
            filename = self._template_header_media_filename()
            media_id = self.account_id._upload_media_to_meta(
                self.media_file,
                filename,
                self.template_id.header_type,
            )
            return {
                'header_media_url': media_id,
                'header_media_filename': filename,
            }
        if self.template_id.header_media_url or self.template_id.header_media_file:
            return {}
        previous_media = self._previous_template_header_media_kwargs()
        if previous_media:
            return previous_media
        raise UserError(_(
            "%(template)s needs a %(type)s header file before sending. "
            "Upload a file in this wizard or set a default Header Media File on the template."
        ) % {
            'template': self.template_id.display_name,
            'type': self.template_id.header_type,
        })

    def _send_to_recipient(self, phone, partner=False, template_header_media_kwargs=None):
        partner_id = partner.id if partner else False
        if self.template_id:
            template_kwargs = dict(template_header_media_kwargs or {})
            self.account_id.send_message(
                to_number=phone,
                message_type='template',
                template_record=self.template_id,
                partner=partner,
                partner_id=partner_id,
                **template_kwargs,
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

        body = (self.message_body or '').strip()
        if not body:
            raise UserError(_('Please enter a message, select a template, or attach media.'))

        self.account_id.send_message(
            to_number=phone,
            message_type='text',
            body=body,
            partner_id=partner_id,
        )

    def _send_to_chat(self, chat, template_header_media_kwargs=None):
        """Send exactly one message to the chat that opened this wizard."""
        self.ensure_one()
        chat.ensure_one()
        account = chat.account_id
        partner = chat.partner_id
        partner_id = partner.id if partner else False

        if self.template_id:
            template_kwargs = dict(template_header_media_kwargs or {})
            vals = {
                'account_id': account.id,
                'phone_number': chat.phone_number,
                'partner_id': partner_id,
                'chat_id_ref': chat.id,
                'message_type': 'template',
                'body': self.template_id.body,
                'template_id': self.template_id.id,
                'template_name': self.template_id._get_send_template_name(),
                'template_language': self.template_id._get_send_language_code(),
                'direction': 'outbound',
            }
            if template_kwargs.get('header_media_url'):
                vals['media_url'] = template_kwargs['header_media_url']
            if template_kwargs.get('header_media_file'):
                vals['media_file'] = template_kwargs['header_media_file']
            if template_kwargs.get('header_media_filename'):
                vals['media_filename'] = template_kwargs['header_media_filename']
            message = self.env['whatsapp.message'].create(vals)
            message.action_send()
            return

        if self.media_file:
            media_type = self._detect_media_type()
            message = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': chat.phone_number,
                'partner_id': partner_id,
                'chat_id_ref': chat.id,
                'message_type': media_type,
                'body': self.message_body or False,
                'caption': self.message_body if media_type in ('image', 'video', 'document') else False,
                'media_file': self.media_file,
                'media_filename': self.media_filename or 'attachment',
                'direction': 'outbound',
            })
            message.action_send()
            return

        if not self.message_body:
            raise UserError(_('Please enter a message, select a template, or attach media.'))
        message = self.env['whatsapp.message'].create({
            'account_id': account.id,
            'phone_number': chat.phone_number,
            'partner_id': partner_id,
            'chat_id_ref': chat.id,
            'message_type': 'text',
            'body': self.message_body,
            'direction': 'outbound',
        })
        message.action_send()

    def action_send(self):
        """Send WhatsApp message to selected partners or direct phone number"""
        self.ensure_one()
        sent_count = 0
        errors = []

        chat_id = self.env.context.get('default_chat_id')
        if not chat_id and self.env.context.get('active_model') == 'whatsapp.chat':
            chat_id = self.env.context.get('active_id')
        chat = self.env['whatsapp.chat'].browse(chat_id).exists() if chat_id else False
        if chat:
            if self.account_id != chat.account_id:
                self.account_id = chat.account_id
            template_header_media_kwargs = self._prepare_template_header_media_kwargs()
            self._send_to_chat(chat, template_header_media_kwargs=template_header_media_kwargs)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Done',
                    'message': 'WhatsApp message sent to this chat.',
                    'type': 'success',
                    'sticky': False,
                }
            }

        if not self.partner_ids and not self.phone_number:
            raise UserError(_('Please select at least one recipient or enter a Direct Phone Number.'))

        template_header_media_kwargs = self._prepare_template_header_media_kwargs()

        # Send to direct phone number if provided
        if self.phone_number:
            phone = self._normalize_phone(self.phone_number)
            try:
                self._send_to_recipient(phone, template_header_media_kwargs=template_header_media_kwargs)
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
                self._send_to_recipient(
                    phone,
                    partner=partner,
                    template_header_media_kwargs=template_header_media_kwargs,
                )
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
