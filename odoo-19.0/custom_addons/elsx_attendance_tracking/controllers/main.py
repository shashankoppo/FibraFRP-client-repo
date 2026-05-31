# -*- coding: utf-8 -*-

import ipaddress

from requests.exceptions import RequestException

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.hr_attendance.controllers.main import HrAttendance as BaseHrAttendance


def _first_header_ip(header_value):
    if not header_value:
        return False
    return header_value.split(',')[0].strip()


def _clean_ip(candidate):
    if not candidate:
        return False
    value = str(candidate).strip()
    if not value:
        return False
    if value.startswith('[') and ']' in value:
        value = value[1:value.index(']')]
    elif ':' in value and value.count(':') == 1:
        value = value.rsplit(':', 1)[0]
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return value


def _is_public_ip(ip_value):
    try:
        parsed = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def _request_header(name):
    return request.httprequest.headers.get(name)


def _best_client_ip():
    candidates = [
        _request_header('CF-Connecting-IP'),
        _request_header('True-Client-IP'),
        _request_header('X-Real-IP'),
        _first_header_ip(_request_header('X-Forwarded-For')),
        _request_header('X-Client-IP'),
        getattr(request.geoip, 'ip', False),
        request.httprequest.remote_addr,
    ]
    cleaned = [_clean_ip(candidate) for candidate in candidates]
    cleaned = [candidate for candidate in cleaned if candidate]
    for candidate in cleaned:
        if _is_public_ip(candidate):
            return candidate
    return cleaned[0] if cleaned else False


def _geoip_location_attr(name):
    location = getattr(request.geoip, 'location', False)
    return getattr(location, name, False) if location else False


def _get_geoip_response(mode, latitude=False, longitude=False, device_tracking_enabled=True):
    response = {'mode': mode}
    if not device_tracking_enabled:
        return response

    latitude = latitude or _geoip_location_attr('latitude') or False
    longitude = longitude or _geoip_location_attr('longitude') or False

    try:
        location = request.env['base.geocoder']._get_localisation(latitude, longitude)
    except (UserError, RequestException):
        location = _("Unknown")

    user_agent = request.httprequest.user_agent
    browser = user_agent.browser or user_agent.string or _("Unknown")

    response.update({
        'location': location or _("Unknown"),
        'latitude': latitude,
        'longitude': longitude,
        'ip_address': _best_client_ip(),
        'browser': browser[:128],
    })
    return response


class HrAttendance(BaseHrAttendance):
    _get_geoip_response = staticmethod(_get_geoip_response)


# Existing hr_attendance routes may already be registered on the base
# controller. Patch only the helper used by those routes so tunnel-aware
# tracking works without replacing any check-in/check-out endpoint.
BaseHrAttendance._get_geoip_response = staticmethod(_get_geoip_response)
