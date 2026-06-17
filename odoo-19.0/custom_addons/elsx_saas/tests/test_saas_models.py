# -*- coding: utf-8 -*-
"""
Unit tests for ELSx SaaS module
"""
from datetime import datetime, timedelta
from odoo.tests import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestSaaSTenant(TransactionCase):
    """Test cases for SaaS Tenant model"""

    def setUp(self):
        super().setUp()
        self.tenant_model = self.env['elsx.saas.tenant']
        self.plan_model = self.env['elsx.saas.billing.plan']

    def test_tenant_creation(self):
        """Test basic tenant creation"""
        tenant = self.tenant_model.create({
            'name': 'Test Startup',
            'admin_email': 'admin@teststartup.com',
            'plan': 'starter',
        })
        self.assertEqual(tenant.name, 'Test Startup')
        self.assertEqual(tenant.state, 'draft')
        self.assertIn('elsx_test', tenant.db_name)

    def test_tenant_db_name_generation(self):
        """Test database name auto-generation"""
        tenant = self.tenant_model.create({
            'name': 'Tech Startup Inc.',
            'admin_email': 'admin@example.com',
        })
        # Should slugify: Tech Startup Inc. → elsx_tech_startup_inc
        self.assertTrue(tenant.db_name.startswith('elsx_'))
        self.assertNotIn(' ', tenant.db_name)
        self.assertNotIn('.', tenant.db_name)

    def test_invalid_email_validation(self):
        """Test email validation"""
        with self.assertRaises(ValidationError):
            self.tenant_model.create({
                'name': 'Bad Email Test',
                'admin_email': 'not-an-email',
                'plan': 'starter',
            })

    def test_tenant_state_transitions(self):
        """Test tenant state transitions"""
        tenant = self.tenant_model.create({
            'name': 'State Test',
            'admin_email': 'admin@test.com',
            'backup_verified': True,
            'plan': 'starter',
        })

        # Test request provisioning
        tenant.action_request_provisioning()
        self.assertEqual(tenant.state, 'requested')

        # Mark provisioning
        tenant.action_mark_provisioning()
        self.assertEqual(tenant.state, 'provisioning')

        # Mark active (should fail - missing checkscheck)
        tenant.client_database_created = True
        tenant.modules_upgraded = True
        tenant.action_mark_active()
        self.assertEqual(tenant.state, 'active')

    def test_provisioning_without_backup_fails(self):
        """Test that provisioning fails without backup verification"""
        tenant = self.tenant_model.create({
            'name': 'No Backup Test',
            'admin_email': 'admin@test.com',
            'backup_verified': False,
            'plan': 'starter',
        })

        with self.assertRaises(UserError):
            tenant.action_request_provisioning()

    def test_module_selection(self):
        """Test module selection based on plan"""
        tenant = self.tenant_model.create({
            'name': 'Module Test',
            'admin_email': 'admin@test.com',
            'plan': 'starter',
            'enable_crm': True,
            'enable_accounting': True,
            'enable_whatsapp': False,
        })

        modules = tenant._selected_modules()
        self.assertIn('elsx_client_restrictions', modules)
        self.assertIn('crm', modules)
        self.assertIn('account', modules)
        self.assertNotIn('elsx_whatsapp_marketing', modules)


class TestSaaSAPIToken(TransactionCase):
    """Test cases for SaaS API Token model"""

    def setUp(self):
        super().setUp()
        self.token_model = self.env['elsx.saas.api.token']
        self.tenant_model = self.env['elsx.saas.tenant']

        # Create test tenant
        self.tenant = self.tenant_model.create({
            'name': 'API Test Tenant',
            'admin_email': 'admin@apitest.com',
            'plan': 'business',
        })

    def test_token_creation(self):
        """Test API token creation"""
        token = self.token_model.create({
            'tenant_id': self.tenant.id,
            'description': 'Test Integration',
            'permissions': 'read_only',
        })

        self.assertEqual(token.tenant_id, self.tenant)
        self.assertTrue(token.is_active)
        self.assertIsNotNone(token.token_key)
        self.assertIsNotNone(token.token_secret)
        self.assertTrue(token.token_key.startswith('elsx_'))

    def test_token_expiry_calculation(self):
        """Test token expiry calculations"""
        future_date = datetime.today().date() + timedelta(days=30)
        token = self.token_model.create({
            'tenant_id': self.tenant.id,
            'expires_on': future_date,
        })

        self.assertEqual(token.days_until_expiry, 30)

    def test_token_regeneration(self):
        """Test token key regeneration"""
        token = self.token_model.create({
            'tenant_id': self.tenant.id,
        })

        original_key = token.token_key
        token.action_regenerate_token()

        self.assertNotEqual(token.token_key, original_key)
        self.assertTrue(token.is_active)

    def test_token_deactivation(self):
        """Test token deactivation"""
        token = self.token_model.create({
            'tenant_id': self.tenant.id,
        })

        self.assertTrue(token.is_active)
        token.action_deactivate()
        self.assertFalse(token.is_active)


class TestSaasHealth(TransactionCase):
    """Test cases for SaaS Health Check model"""

    def setUp(self):
        super().setUp()
        self.health_model = self.env['elsx.saas.health.check']
        self.tenant_model = self.env['elsx.saas.tenant']

        self.tenant = self.tenant_model.create({
            'name': 'Health Test',
            'admin_email': 'admin@healthtest.com',
        })

    def test_health_check_recording(self):
        """Test recording a health check"""
        status_dict = {
            'http_status': 200,
            'is_reachable': True,
            'response_time_ms': 45.3,
            'db_reachable': True,
            'db_connection_time_ms': 12.5,
            'filestore_status': 'ok',
            'critical_modules_active': True,
            'overall_status': 'ok',
            'has_alerts': False,
        }

        health = self.health_model.record_health_check(self.tenant.id, status_dict)

        self.assertEqual(health.overall_status, 'ok')
        self.assertTrue(health.is_reachable)
        self.assertEqual(health.http_status, 200)
        self.assertEqual(self.tenant.health_status, 'ok')


class TestSaasUsageTracking(TransactionCase):
    """Test cases for SaaS Usage Tracking model"""

    def setUp(self):
        super().setUp()
        self.usage_model = self.env['elsx.saas.tenant.usage']
        self.tenant_model = self.env['elsx.saas.tenant']

        self.tenant = self.tenant_model.create({
            'name': 'Usage Test',
            'admin_email': 'admin@usagetest.com',
            'max_users': 100,
            'storage_quota_gb': 100,
        })

    def test_usage_percentage_calculation(self):
        """Test usage percentage calculations"""
        usage = self.usage_model.create({
            'tenant_id': self.tenant.id,
            'active_users': 80,
            'user_limit': 100,
            'used_storage_gb': 50.0,
            'allocated_storage_gb': 100,
        })

        self.assertEqual(usage.user_limit_percentage, 80)
        self.assertEqual(usage.storage_limit_percentage, 50)

    def test_usage_unique_per_day(self):
        """Test that only one usage record per tenant per day"""
        usage1 = self.usage_model.create({
            'tenant_id': self.tenant.id,
            'active_users': 10,
            'usage_date': datetime.today().date(),
        })

        # Try to create duplicate for same day
        with self.assertRaises(Exception):  # Integrity error
            usage2 = self.usage_model.create({
                'tenant_id': self.tenant.id,
                'active_users': 20,
                'usage_date': datetime.today().date(),
            })


class TestSaasBilling(TransactionCase):
    """Test cases for SaaS Billing models"""

    def setUp(self):
        super().setUp()
        self.plan_model = self.env['elsx.saas.billing.plan']
        self.cycle_model = self.env['elsx.saas.billing.cycle']
        self.sub_model = self.env['elsx.saas.subscription']
        self.tenant_model = self.env['elsx.saas.tenant']

        self.tenant = self.tenant_model.create({
            'name': 'Billing Test',
            'admin_email': 'admin@billingtest.com',
        })

    def test_billing_plan_creation(self):
        """Test billing plan creation"""
        plan = self.plan_model.create({
            'name': 'Test Plan',
            'code': 'test_plan',
            'monthly_price': 100,
            'annual_price': 1000,
            'max_users': 50,
            'storage_quota_gb': 50,
        })

        self.assertEqual(plan.name, 'Test Plan')
        self.assertEqual(plan.monthly_price, 100)

    def test_annual_discount_validation(self):
        """Test that annual price is validated to be less than 12x monthly"""
        with self.assertRaises(ValidationError):
            self.plan_model.create({
                'name': 'Bad Plan',
                'code': 'bad_plan',
                'monthly_price': 100,
                'annual_price': 1300,  # More than 12x monthly
            })

    def test_invoice_total_calculation(self):
        """Test invoice total amount calculation"""
        plan = self.plan_model.create({
            'name': 'Test',
            'code': 'test',
            'monthly_price': 100,
            'max_users': 10,
            'storage_quota_gb': 10,
        })

        invoice = self.cycle_model.create({
            'tenant_id': self.tenant.id,
            'plan_id': plan.id,
            'billing_cycle': 'monthly',
            'base_amount': 100,
            'setup_fee': 50,
            'tax_amount': 15,
            'discount_amount': 10,
            'cycle_start_date': datetime.today().date(),
            'cycle_end_date': datetime.today().date() + timedelta(days=30),
            'invoice_date': datetime.today().date(),
        })

        expected_total = 100 + 50 + 15 - 10
        self.assertEqual(invoice.total_amount, expected_total)


class TestSaasTicketing(TransactionCase):
    """Test cases for SaaS Support Ticketing"""

    def setUp(self):
        super().setUp()
        self.ticket_model = self.env['elsx.saas.support.ticket']
        self.tenant_model = self.env['elsx.saas.tenant']

        self.tenant = self.tenant_model.create({
            'name': 'Support Test',
            'admin_email': 'admin@supporttest.com',
        })

    def test_ticket_creation(self):
        """Test support ticket creation"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'email': 'test@example.com',
        })

        ticket = self.ticket_model.create({
            'tenant_id': self.tenant.id,
            'name': 'Test Issue',
            'description': 'This is a test issue',
            'category': 'technical',
            'submitted_by': partner.id,
        })

        self.assertEqual(ticket.state, 'new')
        self.assertIsNotNone(ticket.ticket_number)
        self.assertTrue(ticket.ticket_number.startswith('TICKET/'))

    def test_sla_calculation(self):
        """Test SLA timer calculation"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'email': 'test@example.com',
        })

        ticket = self.ticket_model.create({
            'tenant_id': self.tenant.id,
            'name': 'Critical Issue',
            'description': 'System down',
            'category': 'technical',
            'priority': '1',  # Critical - 1 hour SLA
            'submitted_by': partner.id,
        })

        # SLA timer should be approximately 1 hour (3600 seconds)
        self.assertGreater(ticket.sla_timer_hours, 0)
        self.assertLess(ticket.sla_timer_hours, 2)
