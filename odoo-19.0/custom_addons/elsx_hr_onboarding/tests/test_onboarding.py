# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestElsxHrOnboarding(TransactionCase):

    def setUp(self):
        super().setUp()
        # Create a test employee
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Employee John Doe',
        })
        # Create a dummy partner for signing
        self.partner = self.env['res.partner'].create({
            'name': 'John Doe',
            'email': 'john@example.com',
        })
        # Create a test PDF attachment
        self.attachment = self.env['ir.attachment'].create({
            'name': 'NDA.pdf',
            'datas': b'',
            'mimetype': 'application/pdf',
        })
        # Create a sign request for the NDA
        self.sign_request = self.env['elsx.sign.request'].create({
            'name': 'NDA Agreement',
            'document_attachment_id': self.attachment.id,
            'partner_id': self.partner.id,
            'employee_id': self.employee.id,
        })

    def test_create_onboarding_plan(self):
        """Test creating a full onboarding plan with mixed tasks."""
        plan = self.env['elsx.onboarding.plan'].create({
            'name': 'Standard Onboarding',
            'employee_id': self.employee.id,
            'task_ids': [
                (0, 0, {'name': 'IT Setup: Create Email', 'task_type': 'it_setup'}),
                (0, 0, {'name': 'Sign NDA', 'task_type': 'sign_document', 'sign_request_id': self.sign_request.id}),
                (0, 0, {'name': 'Read Employee Handbook', 'task_type': 'read_document'}),
            ]
        })
        self.assertEqual(plan.state, 'draft')
        self.assertEqual(len(plan.task_ids), 3)

    def test_progress_computation(self):
        """Test progress computes correctly based on task completion."""
        plan = self.env['elsx.onboarding.plan'].create({
            'name': 'Progress Test Plan',
            'employee_id': self.employee.id,
            'task_ids': [
                (0, 0, {'name': 'Task A', 'task_type': 'checklist'}),
                (0, 0, {'name': 'Task B', 'task_type': 'checklist'}),
            ]
        })
        self.assertEqual(plan.progress, 0, "Should start at 0%")
        plan.task_ids[0].state = 'done'
        plan._compute_progress()
        self.assertEqual(plan.progress, 50, "After completing 1 of 2 tasks, progress should be 50%")

    def test_prevent_task_done_without_signature(self):
        """Test that a signing task cannot be marked done if document is not signed."""
        plan = self.env['elsx.onboarding.plan'].create({
            'name': 'Sign Test Plan',
            'employee_id': self.employee.id,
            'task_ids': [
                (0, 0, {
                    'name': 'Sign NDA',
                    'task_type': 'sign_document',
                    'sign_request_id': self.sign_request.id
                }),
            ]
        })
        with self.assertRaises(Exception, msg="Should block marking signed task as done when signature is missing"):
            plan.task_ids[0].action_mark_done()

    def test_sign_then_mark_done(self):
        """Test that signing then marking works correctly."""
        plan = self.env['elsx.onboarding.plan'].create({
            'name': 'Full Flow Plan',
            'employee_id': self.employee.id,
            'task_ids': [
                (0, 0, {
                    'name': 'Sign Contract',
                    'task_type': 'sign_document',
                    'sign_request_id': self.sign_request.id
                }),
            ]
        })
        # Simulate a completed signature
        self.sign_request.write({'state': 'signed'})
        # Now should pass
        plan.task_ids[0].action_mark_done()
        self.assertEqual(plan.task_ids[0].state, 'done', "Task should be marked done after doc is signed.")
