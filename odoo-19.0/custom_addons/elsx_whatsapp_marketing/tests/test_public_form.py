from lxml import html
import io
from PIL import Image
from ..controllers.whatsapp_form import WhatsAppPublicFormController
from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestWhatsAppPublicForm(HttpCase):
    def setUp(self):
        super().setUp()
        self.opener.headers['Connection'] = 'close'
        self.form = self.env['whatsapp.form'].create({
            'name': 'Public Form Test', 'require_consent': True,
            'field_ids': [
                (0, 0, {'name': 'Name', 'field_key': 'name', 'field_type': 'text', 'required': True}),
                (0, 0, {'name': 'Consent', 'field_key': 'consent', 'field_type': 'consent'}),
                (0, 0, {'name': 'Attachment', 'field_key': 'attachment', 'field_type': 'file'}),
            ],
        })
        self.env['ir.config_parameter'].set_param('whatsapp.form.rate_limit.ip.seconds', '0')
        self.env['ir.config_parameter'].set_param('whatsapp.form.rate_limit.seconds', '0')
        self.path = '/whatsapp/form/' + self.form.public_token

    def data(self, **values):
        page = self.url_open(self.path)
        self.assertEqual(page.status_code, 200)
        token = html.fromstring(page.content).xpath("//input[@name='csrf_token']/@value")[0]
        return {'csrf_token': token, 'name': 'Test Customer', **values}

    def test_missing_or_false_consent_is_rejected_server_side(self):
        for value in ('', 'false'):
            response = self.url_open(self.path, data=self.data(consent=value))
            self.assertEqual(response.status_code, 400)
        self.assertFalse(self.form.submission_ids)

    def test_forged_image_and_unknown_upload_fields_are_rejected(self):
        response = self.url_open(self.path, data=self.data(consent='on'),
                                 files={'attachment': ('image.png', b'<script>bad</script>', 'image/png')})
        self.assertEqual(response.status_code, 400)
        response = self.url_open(self.path, data=self.data(consent='on'),
                                 files={'unconfigured': ('data.txt', b'test', 'text/plain')})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.form.submission_ids)

    def test_content_validator_rejects_truncated_magic_headers(self):
        controller = WhatsAppPublicFormController()
        self.assertFalse(controller._valid_file_content(b'\x89PNG\r\n\x1a\n', 'image/png'))
        self.assertFalse(controller._valid_file_content(b'%PDF-1.4\n%%EOF', 'application/pdf'))
        image = io.BytesIO()
        Image.new('RGB', (2, 2), 'green').save(image, format='PNG')
        self.assertTrue(controller._valid_file_content(image.getvalue(), 'image/png'))

    def test_submission_audits_ip_agent_and_consent(self):
        response = self.url_open(self.path, data=self.data(consent='on'),
                                 headers={'User-Agent': 'WhatsApp Form Test', 'X-Forwarded-For': '203.0.113.8'})
        self.assertEqual(response.status_code, 200)
        submission = self.form.submission_ids
        self.assertEqual(len(submission), 1)
        self.assertTrue(submission.consent_given)
        self.assertEqual(submission.user_agent, 'WhatsApp Form Test')
        self.assertNotEqual(submission.ip_address, '203.0.113.8')

    def test_repeat_submission_is_throttled_without_session_state(self):
        self.env['ir.config_parameter'].set_param('whatsapp.form.rate_limit.ip.seconds', '30')
        self.assertEqual(self.url_open(self.path, data=self.data(consent='on')).status_code, 200)
        self.opener.cookies.clear()
        self.assertEqual(self.url_open(self.path, data=self.data(consent='on')).status_code, 429)
        self.assertEqual(len(self.form.submission_ids), 1)
