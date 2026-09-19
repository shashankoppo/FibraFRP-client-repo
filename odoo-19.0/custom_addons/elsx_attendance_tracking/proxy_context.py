# -*- coding: utf-8 -*-
"""Trusted client-network metadata for requests arriving through a proxy.

Cloudflare Tunnel supplies CF-Connecting-IP to the local origin.  That header
is useful only after the immediate peer has been verified as an explicitly
configured proxy; accepting it from an arbitrary client would allow IP spoofing.
"""

import ipaddress
import os


def _clean_ip(value):
    """Return a normalized IP address, accepting common proxy host:port forms."""
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    if value.startswith('[') and ']' in value:
        value = value[1:value.index(']')]
    elif value.count(':') == 1:
        host, _, port = value.rpartition(':')
        if host and port.isdigit():
            value = host
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return False


def _trusted_networks(value=None):
    value = os.environ.get('ODOO_TRUSTED_PROXY_CIDRS', '') if value is None else value
    networks = []
    for item in str(value or '').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # A bad entry must fail closed instead of silently trusting traffic.
            continue
    return networks


def _request_peer(httprequest):
    environ = getattr(httprequest, 'environ', {}) or {}
    # Werkzeug ProxyFix replaces REMOTE_ADDR. Its preserved value is the actual
    # immediate peer and is the only value suitable for the trust decision.
    original = environ.get('werkzeug.proxy_fix.orig') or {}
    return _clean_ip(original.get('REMOTE_ADDR') or environ.get('REMOTE_ADDR') or
                     getattr(httprequest, 'remote_addr', False))


def _header(httprequest, name):
    headers = getattr(httprequest, 'headers', {}) or {}
    return headers.get(name) or (getattr(httprequest, 'environ', {}) or {}).get(
        'HTTP_' + name.upper().replace('-', '_'))


def _browser_name(user_agent):
    user_agent = (user_agent or '').lower()
    if 'edg/' in user_agent or 'edge/' in user_agent:
        return 'Microsoft Edge'
    if 'opr/' in user_agent or 'opera' in user_agent:
        return 'Opera'
    if 'firefox/' in user_agent:
        return 'Firefox'
    if 'chrome/' in user_agent or 'crios/' in user_agent:
        return 'Chrome'
    if 'safari/' in user_agent:
        return 'Safari'
    return 'Unknown browser'


def _device_name(user_agent):
    user_agent = (user_agent or '').lower()
    if 'ipad' in user_agent or 'tablet' in user_agent:
        return 'Tablet'
    if any(token in user_agent for token in ('mobi', 'iphone', 'android')):
        return 'Mobile'
    if user_agent:
        return 'Desktop'
    return 'Unknown device'


def _platform_name(user_agent, client_platform=None):
    hint = (client_platform or '').strip().strip('"')
    if hint:
        return hint[:48]
    user_agent = (user_agent or '').lower()
    if 'windows' in user_agent:
        return 'Windows'
    if 'iphone' in user_agent or 'ipad' in user_agent or 'ios' in user_agent:
        return 'iOS'
    if 'android' in user_agent:
        return 'Android'
    if 'mac os' in user_agent or 'macintosh' in user_agent:
        return 'macOS'
    if 'linux' in user_agent:
        return 'Linux'
    return 'Unknown platform'


def resolve_client_context(httprequest):
    """Return IP and device metadata without trusting user-controlled headers.

    ``ODOO_TRUSTED_PROXY_CIDRS`` is intentionally opt-in. When it is unset,
    the direct network peer is retained and all forwarding headers are ignored.
    """
    peer = _request_peer(httprequest)
    trusted = False
    if peer:
        parsed_peer = ipaddress.ip_address(peer)
        trusted = any(parsed_peer in network for network in _trusted_networks())

    client_ip = peer
    source = 'direct'
    if trusted:
        cloudflare_ip = _clean_ip(_header(httprequest, 'CF-Connecting-IP'))
        if cloudflare_ip:
            client_ip = cloudflare_ip
            source = 'cloudflare_tunnel'
        else:
            # A trusted non-Cloudflare reverse proxy is still useful for audit,
            # but its address is retained rather than accepting a spoofable XFF.
            source = 'trusted_proxy'

    user_agent = (_header(httprequest, 'User-Agent') or '')[:512]
    platform = _platform_name(user_agent, _header(httprequest, 'Sec-CH-UA-Platform'))
    device = _device_name(user_agent)
    browser = _browser_name(user_agent)
    return {
        'ip_address': client_ip or False,
        'ip_source': source,
        'peer_ip': peer or False,
        'user_agent': user_agent,
        'browser': browser,
        'device': ('%s / %s / %s' % (device, platform, browser))[:160],
    }
