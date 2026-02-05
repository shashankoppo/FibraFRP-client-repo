from odoo import models, fields, api
import hashlib
import json
from datetime import datetime

class ELSXBlockchainLog(models.Model):
    _name = 'elsx.blockchain.log'
    _description = 'ELSX Tamper-Proof Audit Log'
    _order = 'id desc'

    model_name = fields.Char('Model', required=True, readonly=True)
    res_id = fields.Integer('Resource ID', required=True, readonly=True)
    operation = fields.Selection([('create', 'Create'), ('write', 'Update'), ('unlink', 'Delete')], 'Operation', readonly=True)
    data_snapshot = fields.Text('Data JSON', readonly=True)
    previous_hash = fields.Char('Previous Hash', readonly=True)
    current_hash = fields.Char('Current Hash', readonly=True, index=True)
    timestamp = fields.Datetime('Timestamp', default=fields.Datetime.now, readonly=True)
    is_verified = fields.Boolean('Verified', compute='_compute_verification', store=True)

    @api.depends('current_hash', 'previous_hash', 'data_snapshot')
    def _compute_verification(self):
        for record in self:
            # Simple verification logic
            recalculated = self._generate_hash(record.previous_hash, record.data_snapshot, record.operation, record.timestamp)
            record.is_verified = (recalculated == record.current_hash)

    def _generate_hash(self, prev_hash, data, op, ts):
        content = f"{prev_hash}{data}{op}{ts}"
        return hashlib.sha256(content.encode()).hexdigest()

class BaseBlockchain(models.AbstractModel):
    _inherit = 'base'

    def _get_blockchain_data(self):
        """Standard method to get fields for hashing"""
        return {f: self[f] for f in self._fields if not self._fields[f].compute and f != 'write_date'}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._name in ['sale.order', 'account.move', 'account.payment']:
            for record in records:
                record._log_to_blockchain('create')
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._name in ['sale.order', 'account.move', 'account.payment']:
            for record in self:
                record._log_to_blockchain('write')
        return res

    def _log_to_blockchain(self, operation):
        last_log = self.env['elsx.blockchain.log'].search([], order='id desc', limit=1)
        prev_hash = last_log.current_hash if last_log else "GENESIS_ELSX"
        
        data = json.dumps(self.read()[0], default=str)
        timestamp = fields.Datetime.now()
        
        content = f"{prev_hash}{data}{operation}{timestamp}"
        curr_hash = hashlib.sha256(content.encode()).hexdigest()
        
        self.env['elsx.blockchain.log'].create({
            'model_name': self._name,
            'res_id': self.id,
            'operation': operation,
            'data_snapshot': data,
            'previous_hash': prev_hash,
            'current_hash': curr_hash,
            'timestamp': timestamp,
        })
