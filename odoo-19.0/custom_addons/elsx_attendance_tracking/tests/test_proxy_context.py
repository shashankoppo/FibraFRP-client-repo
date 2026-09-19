# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

from odoo.addons.elsx_attendance_tracking.proxy_context import resolve_client_context


class Request:
    def __init__(self, peer, headers=None, original_peer=None):
        self.remote_addr = peer
        self.headers = headers or {}
        self.environ = {'REMOTE_ADDR': peer}
        if original_peer:
            self.environ['werkzeug.proxy_fix.orig'] = {'REMOTE_ADDR': original_peer}


class TestTrustedProxyContext(unittest.TestCase):
    def test_cloudflare_ip_is_used_only_from_configured_proxy(self):
        request = Request('172.18.0.2', {'CF-Connecting-IP': '203.0.113.9'})
        with patch.dict(os.environ, {'ODOO_TRUSTED_PROXY_CIDRS': '172.18.0.0/16'}):
            context = resolve_client_context(request)
        self.assertEqual(context['ip_address'], '203.0.113.9')
        self.assertEqual(context['ip_source'], 'cloudflare_tunnel')

    def test_forwarded_ip_is_ignored_from_an_untrusted_peer(self):
        request = Request('198.51.100.4', {'CF-Connecting-IP': '203.0.113.9'})
        with patch.dict(os.environ, {'ODOO_TRUSTED_PROXY_CIDRS': '172.18.0.0/16'}):
            context = resolve_client_context(request)
        self.assertEqual(context['ip_address'], '198.51.100.4')
        self.assertEqual(context['ip_source'], 'direct')

    def test_proxyfix_original_peer_controls_the_trust_decision(self):
        request = Request('203.0.113.9', {'CF-Connecting-IP': '203.0.113.9'}, original_peer='172.18.0.2')
        with patch.dict(os.environ, {'ODOO_TRUSTED_PROXY_CIDRS': '172.18.0.0/16'}):
            context = resolve_client_context(request)
        self.assertEqual(context['ip_address'], '203.0.113.9')
        self.assertEqual(context['ip_source'], 'cloudflare_tunnel')

    def test_device_label_does_not_depend_on_client_hints(self):
        request = Request('198.51.100.4', {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36',
        })
        context = resolve_client_context(request)
        self.assertEqual(context['device'], 'Mobile / Android / Chrome')
