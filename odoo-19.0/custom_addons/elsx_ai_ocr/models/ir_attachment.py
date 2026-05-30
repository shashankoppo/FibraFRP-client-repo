# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._queue_elsx_ocr_jobs()
        return records

    def _queue_elsx_ocr_jobs(self):
        """Queue OCR work for review instead of calling AI synchronously or writing bills."""
        if 'elsx.ai.job' not in self.env.registry.models:
            _logger.info("ELSX OCR skipped: elsx.ai.job model is not installed.")
            return

        supported = {'application/pdf', 'image/jpeg', 'image/png'}
        for attachment in self:
            if attachment.res_model != 'account.move' or attachment.mimetype not in supported or not attachment.res_id:
                continue
            move = self.env['account.move'].browse(attachment.res_id)
            if not move.exists():
                continue
            payload = {
                'attachment_id': attachment.id,
                'attachment_name': attachment.name,
                'mimetype': attachment.mimetype,
                'move_id': move.id,
                'move_name': move.name,
            }
            self.env['elsx.ai.job'].sudo().create_job(
                'ocr',
                'OCR review for %s' % (attachment.name or move.display_name),
                origin=move,
                input_payload=json.dumps(payload, ensure_ascii=False, indent=2),
            )
