import base64
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase

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


class TestWhatsAppContactImport(TransactionCase):
    def test_email_and_new_tag_import_together(self):
        result = self.env['whatsapp.contact'].load(
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
