"""Durable dispatch evidence survives a message worker transaction rollback."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta


class WhatsAppSendAttempt(models.Model):
    _name = 'whatsapp.send.attempt'
    _description = 'WhatsApp Dispatch Evidence'
    _order = 'write_date desc, id desc'

    # Integer references allow reservation before the originating transaction commits.
    account_ref = fields.Integer(required=True, index=True, readonly=True)
    company_ref = fields.Integer(required=True, index=True, readonly=True)
    message_ref = fields.Integer(required=True, index=True, readonly=True)
    state = fields.Selection([('pending', 'Dispatching'), ('accepted', 'Accepted by Meta'),
                              ('rejected', 'Rejected'), ('uncertain', 'Needs Review')], readonly=True)
    wamid = fields.Char(readonly=True)
    detail = fields.Char(readonly=True)
    _dispatch_identity = models.Constraint('unique(account_ref, message_ref)', 'Dispatch identity must be unique.')

    @api.model
    def _reserve(self, message):
        with self.env.registry.cursor() as cr:
            cr.execute('''INSERT INTO whatsapp_send_attempt
                (account_ref, company_ref, message_ref, state, create_date, write_date)
                VALUES (%s, %s, %s, 'pending', NOW(), NOW())
                ON CONFLICT (account_ref, message_ref) DO UPDATE SET state='pending', write_date=NOW()
                WHERE whatsapp_send_attempt.state='rejected' AND whatsapp_send_attempt.wamid IS NULL
                RETURNING id''', [message.account_id.id, message.account_id.company_id.id, message.id])
            reserved = cr.fetchone()
            cr.execute('SELECT state, wamid FROM whatsapp_send_attempt WHERE account_ref=%s AND message_ref=%s',
                       [message.account_id.id, message.id])
            state, wamid = cr.fetchone()
            cr.commit()
        return bool(reserved), state, wamid

    @api.model
    def _finish(self, message, state, wamid=None, detail=None):
        with self.env.registry.cursor() as cr:
            cr.execute('''UPDATE whatsapp_send_attempt SET state=%s, wamid=COALESCE(%s, wamid),
                          detail=%s, write_date=NOW() WHERE account_ref=%s AND message_ref=%s
                          AND (state != 'accepted' OR %s = 'accepted')''',
                       [state, wamid, detail, message.account_id.id, message.id, state])
            cr.commit()

    def action_confirm_not_sent(self):
        self.check_access('write')
        if not self.env.user.has_group('elsx_whatsapp_marketing.group_whatsapp_manager'):
            raise UserError(_('Only a WhatsApp manager can resolve uncertain dispatches.'))
        for attempt in self:
            if attempt.write_date and attempt.write_date > fields.Datetime.now() - timedelta(minutes=2):
                raise UserError(_('Dispatch may still be running. Wait before reconciling it.'))
            if attempt.state not in ('uncertain', 'pending'):
                raise UserError(_('Only unresolved dispatches can be released after checking Meta delivery evidence.'))
            message = self.env['whatsapp.message'].browse(attempt.message_ref).exists()
            if not message or message.account_id.id != attempt.account_ref:
                raise UserError(_('The original message is unavailable. Manual reconciliation is required.'))
            message.check_access('write')
            if message.message_id or message.status in ('sent', 'delivered', 'read'):
                raise UserError(_('Delivery evidence exists; this message cannot be released for resend.'))
            attempt.sudo().write({'state': 'rejected', 'detail': 'Reviewed as not sent by user %s' % self.env.uid})
            message.write({'delivery_uncertain': False, 'next_retry_at': False})

    def write(self, vals):
        if not self.env.su:
            raise UserError(_('Dispatch evidence can only be changed through reconciliation.'))
        return super().write(vals)
