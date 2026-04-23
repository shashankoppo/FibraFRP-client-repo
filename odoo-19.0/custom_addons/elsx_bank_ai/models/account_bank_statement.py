# -*- coding: utf-8 -*-
from odoo import models, api

class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    def action_elsx_auto_reconcile(self):
        """
        Custom button or automated cron job action.
        Hooks into the elsx_bank_ai ML heuristic engine to auto-match lines.
        """
        for statement in self:
            self.env['account.reconciliation.ml'].auto_reconcile_statements(statement.id)
        return True

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def _get_ml_suggested_partner(self):
        """
        Overrides line creation/update to fetch fuzzy partner suggestions.
        """
        for line in self:
            if not line.partner_id and line.payment_ref:
                # Find best partner match
                partners = self.env['res.partner'].search([])
                best_match = None
                highest_ratio = 0.0
                
                for partner in partners:
                    ratio = self.env['account.reconciliation.ml'].fuzzy_match_partner(
                        line.payment_ref, partner.name
                    )
                    if ratio > 0.8: # Confidence threshold
                        if ratio > highest_ratio:
                            highest_ratio = ratio
                            best_match = partner
                
                if best_match:
                    line.partner_id = best_match.id
