# -*- coding: utf-8 -*-

from requests.exceptions import RequestException

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.hr_attendance.controllers.main import HrAttendance as BaseHrAttendance
from odoo.addons.elsx_attendance_tracking.proxy_context import resolve_client_context


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

    client_context = resolve_client_context(request.httprequest)

    response.update({
        'location': location or _("Unknown"),
        'latitude': latitude,
        'longitude': longitude,
        'ip_address': client_context['ip_address'],
        'browser': client_context['device'] or _("Unknown"),
    })
    return response


class HrAttendance(BaseHrAttendance):
    _get_geoip_response = staticmethod(_get_geoip_response)


# Existing hr_attendance routes may already be registered on the base
# controller. Patch only the helper used by those routes so tunnel-aware
# tracking works without replacing any check-in/check-out endpoint.
BaseHrAttendance._get_geoip_response = staticmethod(_get_geoip_response)
