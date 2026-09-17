import base64
import json
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..controllers.whatsapp_webhook import WhatsAppWebhook
from ..models import whatsapp_account as account_module
from ..models.whatsapp_account import WhatsAppAccount


class TestPrivateMediaRecovery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whatsapp.account'].create({
            'name': 'Media Recovery',
            'phone_number': '15550000000',
            'phone_number_id': '123456789',
            'business_account_id': '987654321',
            'access_token': 'test-token',
        })

    def test_private_meta_hosts_are_detected(self):
        self.assertTrue(
            self.account._is_private_meta_media_url(
                'https://scontent.whatsapp.net/v/t62/example.mp4'
            )
        )
        self.assertTrue(
            self.account._is_private_meta_media_url(
                'https://lookaside.fbsbx.com/whatsapp_business/attachments/example'
            )
        )
        self.assertFalse(
            self.account._is_private_meta_media_url(
                'https://cdn.example.com/public/example.mp4'
            )
        )

    def test_nested_template_media_link_becomes_media_id(self):
        payload = {
            'name': 'video_campaign',
            'language': {'code': 'en_US'},
            'components': [{
                'type': 'carousel',
                'cards': [{
                    'index': 0,
                    'components': [{
                        'type': 'header',
                        'parameters': [{
                            'type': 'video',
                            'video': {
                                'link': 'https://scontent.whatsapp.net/v/t62/example.mp4'
                            },
                        }],
                    }],
                }],
            }],
        }

        with patch.object(
            WhatsAppAccount,
            '_download_and_upload_private_media',
            return_value='meta-media-id',
        ) as upload:
            result = self.account._replace_private_media_links(payload)

        media = result['components'][0]['cards'][0]['components'][0]['parameters'][0]['video']
        self.assertEqual(media, {'id': 'meta-media-id'})
        upload.assert_called_once()

    def test_private_download_uses_bearer_token_before_upload(self):
        response = Mock(
            status_code=200,
            content=b'video-bytes',
            headers={'Content-Type': 'video/mp4'},
        )
        with (
            patch.object(account_module.requests, 'get', return_value=response) as download,
            patch.object(
                WhatsAppAccount,
                '_upload_media_to_meta',
                return_value='uploaded-media-id',
            ) as upload,
        ):
            media_id = self.account._download_and_upload_private_media(
                'https://scontent.whatsapp.net/v/t62/example.mp4',
                'video',
                'campaign.mp4',
            )

        self.assertEqual(media_id, 'uploaded-media-id')
        self.assertEqual(
            download.call_args.kwargs['headers']['Authorization'],
            'Bearer test-token',
        )
        self.assertEqual(upload.call_args.args[0], base64.b64encode(b'video-bytes'))
        self.assertEqual(upload.call_args.args[1:], ('campaign.mp4', 'video'))

    def test_matching_expired_link_uses_local_file(self):
        media_url = 'https://scontent.whatsapp.net/v/t62/expired.mp4'
        media_file = base64.b64encode(b'local-video-bytes')
        payload = {'video': {'link': media_url}}

        with (
            patch.object(
                WhatsAppAccount,
                '_upload_media_to_meta',
                return_value='reuploaded-media-id',
            ) as upload,
            patch.object(
                WhatsAppAccount,
                '_download_and_upload_private_media',
            ) as download,
        ):
            result = self.account._replace_private_media_links(
                payload,
                filename='campaign.mp4',
                fallback_media_file=media_file,
                fallback_media_url=media_url,
            )

        self.assertEqual(result['video'], {'id': 'reuploaded-media-id'})
        upload.assert_called_once_with(media_file, 'campaign.mp4', 'video')
        download.assert_not_called()

    def test_upload_uses_mime_type(self):
        response = Mock(
            status_code=200,
            content=b'{"id": "uploaded-media-id"}',
        )
        response.json.return_value = {'id': 'uploaded-media-id'}
        with patch.object(account_module.requests, 'post', return_value=response) as post:
            media_id = self.account._upload_media_to_meta(
                base64.b64encode(b'video-bytes'),
                'campaign.mp4',
                'video',
            )

        self.assertEqual(media_id, 'uploaded-media-id')
        self.assertEqual(post.call_args.kwargs['data']['type'], 'video/mp4')

    def test_public_media_link_is_left_unchanged(self):
        payload = {'image': {'link': 'https://cdn.example.com/public/image.jpg'}}
        with patch.object(
            WhatsAppAccount,
            '_download_and_upload_private_media',
        ) as upload:
            result = self.account._replace_private_media_links(payload)

        self.assertEqual(result, payload)
        upload.assert_not_called()

    def _document_template(self, **values):
        return self.env['whatsapp.template'].create({
            'name': 'document_media_test',
            'meta_template_name': 'document_media_test',
            'account_id': self.account.id,
            'language': 'en_US',
            'language_code': 'en_US',
            'body': 'Document media test',
            'header_type': 'document',
            'header_media_filename': 'brochure.pdf',
            **values,
        })

    def _sync_document_sample(self, media_url):
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{
            'id': 'meta-document-test',
            'name': 'document_media_test',
            'language': 'en_US',
            'status': 'APPROVED',
            'category': 'MARKETING',
            'components': [
                {'type': 'BODY', 'text': 'Document media test'},
                {'type': 'HEADER', 'format': 'DOCUMENT',
                 'example': {'header_handle': [media_url]}},
            ],
        }]}
        with patch.object(account_module.requests, 'get', return_value=response):
            self.account.action_sync_templates()

    def test_sync_preserves_configured_media(self):
        template = self._document_template()
        local_file = base64.b64encode(b'local-pdf-bytes')
        for saved_url, saved_file in (
            ('123456789', False),
            ('https://cdn.example.com/brochure.pdf', False),
            ('https://scontent.whatsapp.net/old.pdf', local_file),
            (False, local_file),
        ):
            with self.subTest(saved_url=saved_url):
                template.write({'header_media_url': saved_url, 'header_media_file': saved_file})
                self._sync_document_sample('https://scontent.whatsapp.net/new.pdf')
                self.assertEqual(template.header_media_url, saved_url)
                self.assertEqual(template.header_media_file, saved_file)
                self.assertEqual(template.header_media_filename, 'brochure.pdf')

    def test_sync_refreshes_sample_when_no_durable_source_exists(self):
        sample_url = 'https://scontent.whatsapp.net/new.pdf'
        self._sync_document_sample(sample_url)
        template = self.env['whatsapp.template'].search([
            ('account_id', '=', self.account.id),
            ('meta_template_name', '=', 'document_media_test'),
        ])
        self.assertEqual(len(template), 1)
        self.assertEqual(template.header_media_url, sample_url)
        template.header_media_url = 'https://scontent.whatsapp.net/old.pdf'
        self._sync_document_sample(sample_url)
        self.assertEqual(template.header_media_url, sample_url)

    def test_saved_file_recovers_temporary_template_link(self):
        local_file = base64.b64encode(b'local-pdf-bytes')
        template = self._document_template(
            header_media_url='https://scontent.whatsapp.net/expired.pdf',
            header_media_file=local_file,
        )
        with (
            patch.object(WhatsAppAccount, '_upload_media_to_meta', return_value='123456789') as upload,
            patch.object(account_module.requests, 'get') as download,
        ):
            first = template._resolve_header_media_value('document')
            second = template._resolve_header_media_value('document')
        self.assertEqual(first, '123456789')
        self.assertEqual(second, first)
        upload.assert_called_once_with(local_file, 'brochure.pdf', 'document')
        download.assert_not_called()
        self.assertEqual(template.header_media_file, local_file)

    def test_explicit_media_override_is_not_replaced_by_template_file(self):
        template = self._document_template(
            header_media_url='https://scontent.whatsapp.net/expired.pdf',
            header_media_file=base64.b64encode(b'template-pdf-bytes'),
        )
        with patch.object(WhatsAppAccount, '_upload_media_to_meta') as upload:
            result = template._resolve_header_media_value(
                'document', media_url='987654321', account=self.account,
            )
        self.assertEqual(result, '987654321')
        upload.assert_not_called()

    def test_expired_link_without_file_fails_without_sending(self):
        template = self._document_template(
            header_media_url='https://scontent.whatsapp.net/expired.pdf',
        )
        response = Mock(status_code=403, content=b'Forbidden')
        with (
            patch.object(account_module.requests, 'get', return_value=response),
            patch.object(account_module.requests, 'post') as send,
        ):
            value = template._resolve_header_media_value('document')
            with self.assertRaisesRegex(UserError, 'HTTP 403'):
                self.account._replace_private_media_links({'document': {'link': value}})
        send.assert_not_called()
        self.assertEqual(template.header_media_url, value)
        self.assertFalse(template.header_media_file)

    def test_blank_chat_opens_prefilled_contact_setup(self):
        chat = self.env['whatsapp.chat'].create({
            'account_id': self.account.id,
            'phone_number': '15550000002',
        })

        action = chat.action_open_contact()

        self.assertEqual(action['res_model'], 'whatsapp.contact')
        self.assertEqual(action['context']['default_phone_number'], '15550000002')
        self.assertFalse(action['context']['default_opt_in'])

    def test_existing_contact_opens_from_chat(self):
        contact = self.env['whatsapp.contact'].create({
            'name': 'Existing Contact',
            'phone_number': '15550000003',
        })
        chat = self.env['whatsapp.chat'].create({
            'account_id': self.account.id,
            'phone_number': '15550000003',
        })

        action = chat.action_open_contact()

        self.assertEqual(action['res_model'], 'whatsapp.contact')
        self.assertEqual(action['res_id'], contact.id)

    def test_send_wizard_exposes_contact_setup_for_blank_chat(self):
        chat = self.env['whatsapp.chat'].create({
            'account_id': self.account.id,
            'phone_number': '15550000004',
        })
        wizard = self.env['whatsapp.send.wizard'].with_context(
            default_chat_id=chat.id,
        ).create({
            'account_id': self.account.id,
        })

        self.assertEqual(wizard.chat_id, chat)
        self.assertTrue(wizard.recipient_setup_required)
        self.assertEqual(wizard.action_open_chat_contact()['res_model'], 'whatsapp.contact')

    def test_send_wizard_respects_account_opt_in_policy(self):
        chat = self.env['whatsapp.chat'].create({
            'account_id': self.account.id,
            'phone_number': '15550000005',
        })
        self.env['whatsapp.compliance.policy'].create({
            'name': 'Legacy direct sends',
            'account_id': self.account.id,
            'require_opt_in': False,
        })
        wizard = self.env['whatsapp.send.wizard'].with_context(
            default_chat_id=chat.id,
        ).create({
            'account_id': self.account.id,
        })

        self.assertFalse(wizard.recipient_setup_required)

    def test_template_sync_reads_all_pages_and_clears_stale_buttons(self):
        template = self.env['whatsapp.template'].create({
            'name': 'Existing Template',
            'meta_template_name': 'existing_template',
            'account_id': self.account.id,
            'language': 'en_US',
            'status': 'approved',
            'body': 'Old body',
            'has_buttons': True,
            'button_type': 'quick_reply',
            'button_text_1': 'Old button',
        })
        first = Mock(status_code=200)
        first.json.return_value = {
            'data': [{
                'id': 'meta-existing',
                'name': 'existing_template',
                'language': 'en_US',
                'status': 'APPROVED',
                'category': 'MARKETING',
                'components': [{'type': 'BODY', 'text': 'Fresh body'}],
            }],
            'paging': {'next': 'https://graph.facebook.com/next-page'},
        }
        second = Mock(status_code=200)
        second.json.return_value = {
            'data': [{
                'id': 'meta-second',
                'name': 'second_template',
                'language': 'en_US',
                'status': 'APPROVED',
                'category': 'UTILITY',
                'components': [{'type': 'BODY', 'text': 'Second body'}],
            }],
        }

        with patch.object(account_module.requests, 'get', side_effect=[first, second]) as request:
            self.account.action_sync_templates()

        template.invalidate_recordset()
        self.assertEqual(request.call_count, 2)
        self.assertEqual(template.body, 'Fresh body')
        self.assertFalse(template.has_buttons)
        self.assertFalse(template.button_text_1)
        self.assertTrue(self.env['whatsapp.template'].search([
            ('account_id', '=', self.account.id),
            ('meta_template_name', '=', 'second_template'),
        ]))

    def test_received_webhook_can_be_replayed_through_normal_dispatcher(self):
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'field': 'messages',
                    'value': {
                        'metadata': {'phone_number_id': self.account.phone_number_id},
                        'messages': [],
                    },
                }],
            }],
        }
        log = self.env['whatsapp.webhook.log'].create({
            'account_id': self.account.id,
            'event_type': 'waba_webhook',
            'status': 'received',
            'raw_payload': json.dumps(payload),
        })

        with patch.object(WhatsAppWebhook, '_dispatch_change') as dispatch:
            self.assertTrue(log._process_received_payload())

        self.assertEqual(log.status, 'processed')
        dispatch.assert_called_once()
        self.assertEqual(dispatch.call_args.args[1], self.account)
        self.assertEqual(dispatch.call_args.args[2], 'messages')

    def test_replayed_webhook_does_not_contend_on_account_freshness(self):
        replay_env = self.env(context={
            **self.env.context,
            'whatsapp_webhook_replay': True,
        })
        account = self.account.with_env(replay_env)
        account.last_webhook_at = False

        WhatsAppWebhook()._touch_account_webhook(replay_env, account)

        self.account.invalidate_recordset(['last_webhook_at'])
        self.assertFalse(self.account.last_webhook_at)

    def test_status_freshness_is_rate_limited_during_webhook_bursts(self):
        checked_at = fields.Datetime.now()
        self.account.write({
            'last_status_webhook_at': checked_at,
            'last_status_wamid': 'wamid-before-burst',
        })

        WhatsAppWebhook()._touch_account_webhook(
            self.env,
            self.account,
            status_wamid='wamid-during-burst',
        )

        self.account.invalidate_recordset(['last_status_webhook_at', 'last_status_wamid'])
        self.assertEqual(self.account.last_status_webhook_at, checked_at)
        self.assertEqual(self.account.last_status_wamid, 'wamid-before-burst')

    def test_webhook_recovery_detects_postgres_serialization_code(self):
        class SerializationError(Exception):
            pgcode = '40001'

        self.assertTrue(
            self.env['whatsapp.webhook.log']._is_serialization_failure(
                SerializationError('retry transaction')
            )
        )


class TestWhatsAppContactImport(TransactionCase):
    def test_email_and_new_tag_import_together(self):
        result = self.env['whatsapp.contact'].with_context(name_create_enabled_fields={'tag_ids': True}).load(
            ['name', 'phone_number', 'email', 'tag_ids'],
            [[
                'Rohit Karday',
                '9881934777',
                'indryansteel@gmail.com',
                'Fibera_CN_2025',
            ]],
        )

        self.assertFalse(result['messages'])
        contact = self.env['whatsapp.contact'].browse(result['ids'])
        self.assertEqual(contact.email, 'indryansteel@gmail.com')
        self.assertEqual(contact.tag_ids.name, 'Fibera_CN_2025')
