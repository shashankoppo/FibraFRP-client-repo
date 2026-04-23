# -*- coding: utf-8 -*-
from odoo import models, fields, api
import difflib
import re

class AccountReconciliationML(models.TransientModel):
    _name = 'account.reconciliation.ml'
    _description = 'Bank Reconciliation ML Heuristics Engine'

    @api.model
    def fuzzy_match_partner(self, payment_ref, partner_name):
        """
        Uses Python's SequenceMatcher to act as a fallback when exact Partner matching fails.
        """
        if not payment_ref or not partner_name:
            return 0.0
        
        # Clean both strings (lowercase, remove special chars)
        clean_ref = re.sub(r'[^a-z0-9 ]', '', payment_ref.lower())
        clean_partner = re.sub(r'[^a-z0-9 ]', '', partner_name.lower())
        
        ratio = difflib.SequenceMatcher(None, clean_ref, clean_partner).ratio()
        return ratio

    @api.model
    def auto_reconcile_statements(self, statement_id):
        """
        Main Engine: Recreates Odoo Enterprise reconciliation algorithm.
        1. Exact match on Invoice No
        2. Exact amount match for a single open invoice from recognized partner
        3. Fuzzy ML logic matching on payment reference text against Partner names
        """
        # Logic to be fleshed out
        return True
