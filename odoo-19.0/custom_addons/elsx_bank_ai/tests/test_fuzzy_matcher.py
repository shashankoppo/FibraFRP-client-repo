# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase

class TestBankFuzzyMatcher(TransactionCase):

    def setUp(self):
        super(TestBankFuzzyMatcher, self).setUp()
        self.ml_engine = self.env['account.reconciliation.ml']
        
        # Create some dummy partners for testing
        self.partner_amazon = self.env['res.partner'].create({'name': 'Amazon Web Services'})
        self.partner_google = self.env['res.partner'].create({'name': 'Google Cloud Platform'})

    def test_exact_match(self):
        """Test if the exact string returns a highly confident ratio."""
        ratio = self.ml_engine.fuzzy_match_partner('AMAZON WEB SERVICES', self.partner_amazon.name)
        self.assertGreater(ratio, 0.9, "Exact text match (ignoring case) should be > 0.9 confident.")

    def test_fuzzy_match_noisy_bank_string(self):
        """Test if dirty bank text can successfully find the partner."""
        # Realistic bank statement text string
        bank_string = "POS DEBIT 12/04 AMAZON WEB SERVIC SEATTLE WA"
        
        ratio_amazon = self.ml_engine.fuzzy_match_partner(bank_string, self.partner_amazon.name)
        ratio_google = self.ml_engine.fuzzy_match_partner(bank_string, self.partner_google.name)
        
        self.assertGreater(ratio_amazon, ratio_google, "AI should score Amazon higher than Google for the noisy string.")
        
    def test_empty_string_handling(self):
        """Test crash prevention of empty references."""
        ratio = self.ml_engine.fuzzy_match_partner('', self.partner_amazon.name)
        self.assertEqual(ratio, 0.0, "Empty string should safely return 0.0 without crashing.")
