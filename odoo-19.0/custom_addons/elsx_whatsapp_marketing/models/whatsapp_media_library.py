# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import base64
import mimetypes

_logger = logging.getLogger(__name__)


class WhatsAppMediaLibrary(models.Model):
    """WhatsApp Media Library for managing reusable media files"""
    _name = 'whatsapp.media.library'
    _description = 'WhatsApp Media Library'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char('Media Name', required=True)
    description = fields.Text('Description')
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, ondelete='cascade')
    
    # Media file
    media_file = fields.Binary('Media File', required=True)
    media_filename = fields.Char('Filename', required=True)
    media_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
    ], string='Media Type', required=True)
    
    # Media properties
    file_size = fields.Integer('File Size (bytes)', readonly=True)
    mime_type = fields.Char('MIME Type', readonly=True)
    
    # Meta properties
    media_id = fields.Char('Meta Media ID', readonly=True, help='ID returned by Meta after upload')
    media_url = fields.Char('Media URL', readonly=True)
    
    # Organization
    category = fields.Char('Category', help='e.g., Product Photos, Invoices, Certificates')
    tag_ids = fields.Many2many('whatsapp.media.tag', string='Tags')
    
    # Settings
    expiry_date = fields.Date('Expiry Date', help='Optional: Mark when this media should be archived')
    is_reusable = fields.Boolean('Reusable', default=True, help='Allow using in multiple messages/campaigns')
    usage_count = fields.Integer('Times Used', readonly=True, default=0)
    
    # Status
    active = fields.Boolean('Active', default=True)
    upload_status = fields.Selection([
        ('draft', 'Draft'),
        ('uploaded', 'Uploaded to Meta'),
        ('failed', 'Upload Failed'),
    ], default='draft')
    error_message = fields.Text('Error Message')
    
    # Timestamps
    uploaded_date = fields.Datetime('Uploaded Date', readonly=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('media_file') and vals.get('media_filename'):
                # Calculate file size
                file_data = base64.b64decode(vals['media_file'])
                vals['file_size'] = len(file_data)
                
                # Guess MIME type
                mime, _ = mimetypes.guess_type(vals['media_filename'])
                vals['mime_type'] = mime or 'application/octet-stream'
                if vals.get('account_id') and vals.get('media_type'):
                    account = self.env['whatsapp.account'].browse(vals['account_id'])
                    account._check_media_upload_size(vals['media_file'], vals['media_type'], vals.get('media_filename'))
        
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('media_file') or vals.get('media_filename') or vals.get('media_type'):
            for record in self:
                media_file = vals.get('media_file', record.media_file)
                filename = vals.get('media_filename', record.media_filename)
                media_type = vals.get('media_type', record.media_type)
                account = self.env['whatsapp.account'].browse(vals.get('account_id', record.account_id.id))
                if media_file and filename:
                    file_data = base64.b64decode(media_file)
                    vals.setdefault('file_size', len(file_data))
                    mime, _ = mimetypes.guess_type(filename)
                    vals.setdefault('mime_type', mime or 'application/octet-stream')
                    account._check_media_upload_size(media_file, media_type, filename)
        return super().write(vals)
    
    def action_upload_to_meta(self):
        """Upload media to Meta Cloud API"""
        for record in self:
            if not record.account_id:
                record.upload_status = 'failed'
                record.error_message = 'No WhatsApp account selected'
                continue
            
            try:
                media_id = record._upload_to_meta()
                if media_id:
                    record.write({
                        'media_id': media_id,
                        'upload_status': 'uploaded',
                        'uploaded_date': fields.Datetime.now(),
                        'error_message': False,
                    })
                else:
                    record.write({
                        'upload_status': 'failed',
                        'error_message': 'Upload returned no media ID',
                    })
            except Exception as e:
                record.write({
                    'upload_status': 'failed',
                    'error_message': str(e),
                })
                _logger.error(f"Media upload failed: {e}")
    
    def _upload_to_meta(self):
        """Internal method to upload media to Meta"""
        import requests
        import io
        
        self.ensure_one()
        account = self.account_id
        
        url = f"https://graph.facebook.com/{account.api_version}/{account.phone_number_id}/media"
        headers = {
            'Authorization': f'Bearer {account.access_token}',
        }
        
        file_content = base64.b64decode(self.media_file)
        files = {
            'file': (self.media_filename, io.BytesIO(file_content), self.mime_type),
        }
        data = {
            'messaging_product': 'whatsapp',
            'type': self.media_type,
        }
        
        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        
        if response.status_code == 200:
            return response.json().get('id')
        else:
            raise Exception(f"Upload failed: {response.text}")
    
    def action_use_in_message(self):
        """Create a message using this media"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Message with Media',
            'res_model': 'whatsapp.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_account_id': self.account_id.id,
                'default_media_file': self.media_file,
                'default_media_filename': self.media_filename,
                'default_message_type': self.media_type,
            }
        }
    
    def action_bulk_use(self):
        """Use this media in multiple messages/contacts"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send to Multiple Contacts',
            'res_model': 'whatsapp.media.bulk.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_media_id': self.id,
            }
        }


class WhatsAppMediaTag(models.Model):
    """Tags for organizing media library"""
    _name = 'whatsapp.media.tag'
    _description = 'WhatsApp Media Tag'
    _rec_name = 'name'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color', default=1)
    media_ids = fields.Many2many('whatsapp.media.library', string='Media Files')


class WhatsAppMediaBulkWizard(models.TransientModel):
    """Wizard to send media to multiple contacts"""
    _name = 'whatsapp.media.bulk.wizard'
    _description = 'Send Media to Multiple Contacts'

    media_id = fields.Many2one('whatsapp.media.library', required=True)
    account_id = fields.Many2one('whatsapp.account', related='media_id.account_id', readonly=True)
    
    # Recipient selection
    recipient_type = fields.Selection([
        ('contacts', 'Select Contacts'),
        ('segment', 'From Segment'),
        ('tag', 'By Tag'),
        ('all', 'All Contacts'),
    ], default='contacts')
    
    contact_ids = fields.Many2many('res.partner', string='Contacts')
    segment_id = fields.Many2one('whatsapp.contact.segment', string='Segment')
    tag_ids = fields.Many2many(
        'res.partner.category', 
        'whatsapp_media_bulk_tag_rel', 
        'wizard_id', 
        'category_id', 
        string='Tags'
    )
    
    # Message options
    caption = fields.Char('Caption/Message')
    add_contact_name = fields.Boolean('Personalize with Name', help='Add contact name to caption')
    
    def action_send(self):
        """Send media to selected contacts"""
        self.ensure_one()
        
        # Get recipients
        if self.recipient_type == 'contacts':
            partners = self.contact_ids
        elif self.recipient_type == 'segment':
            self.segment_id._compute_contacts()
            partners = self.segment_id.contact_ids
        elif self.recipient_type == 'tag':
            partners = self.env['res.partner'].search([('category_id', 'in', self.tag_ids.ids)])
        else:  # all
            domain = [('phone', '!=', False)]
            if 'mobile' in self.env['res.partner']._fields:
                domain = ['|', ('mobile', '!=', False)] + domain
            partners = self.env['res.partner'].search(domain)
        
        sent_count = 0
        queued_count = 0
        failed_count = 0
        for partner in partners:
            phone = getattr(partner, 'mobile', False) or partner.phone
            if not phone:
                continue
            
            phone = self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id)
            caption = self.caption
            
            if self.add_contact_name:
                caption = f"{partner.name}: {caption}" if caption else partner.name
            
            try:
                message = self.env['whatsapp.message'].create({
                    'account_id': self.account_id.id,
                    'phone_number': phone,
                    'partner_id': partner.id,
                    'message_type': self.media_id.media_type,
                    'media_file': self.media_id.media_file,
                    'media_filename': self.media_id.media_filename,
                    'caption': caption,
                    'direction': 'outbound',
                })
                message.action_send()
                if message.status in ('sent', 'delivered', 'read'):
                    sent_count += 1
                elif message.status == 'queued':
                    queued_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                _logger.error(f"Failed to create message for {partner.name}: {e}")
        
        # Update usage count
        self.media_id.usage_count += sent_count + queued_count
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Media Dispatch Complete',
                'message': f'{sent_count} sent, {queued_count} queued, {failed_count} failed.',
                'type': 'success' if not failed_count else 'warning',
                'sticky': bool(failed_count),
            }
        }
