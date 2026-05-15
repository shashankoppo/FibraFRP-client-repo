# -*- coding: utf-8 -*-

import logging
import re

from stdnum.eu.vat import check_vies

from odoo import api, models


_logger = logging.getLogger(__name__)

EU_VAT_COUNTRY_CODES = {
    'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'EL', 'ES', 'FI', 'FR',
    'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO',
    'SE', 'SI', 'SK', 'XI',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def autocomplete_by_name(self, query, query_country_id, timeout=15):
        if query_country_id is False:
            query_country_id = self.env.company.country_id.id
        query_country_code = self.env['res.country'].browse(query_country_id).code

        response, _error = self.env['iap.autocomplete.api']._request_partner_autocomplete('search_by_name', {
            'query': query,
            'query_country_code': query_country_code,
        }, timeout=timeout)
        if response and not response.get('error'):
            return [
                self._format_data_company(dict(suggestion))
                for suggestion in response.get('data', [])
            ]
        return []

    @api.model
    def autocomplete_by_vat(self, vat, query_country_id, timeout=15):
        query_country_id = query_country_id or self.env.company.country_id.id
        query_country_code = self.env['res.country'].browse(query_country_id).code

        if vies_suggestion := self._autocomplete_vat_from_vies(vat, query_country_code, timeout=timeout):
            return [vies_suggestion]

        response, _error = self.env['iap.autocomplete.api']._request_partner_autocomplete('search_by_vat', {
            'query': vat,
            'query_country_code': query_country_code,
        }, timeout=timeout)
        if response and not response.get('error'):
            return [
                self._format_data_company(dict(suggestion))
                for suggestion in response.get('data', [])
            ]
        return []

    @api.model
    def _autocomplete_vat_from_vies(self, vat, query_country_code=False, timeout=15):
        vies_vat = self._prepare_vies_vat(vat, query_country_code)
        if not vies_vat:
            return {}

        try:
            vies_result = check_vies(vies_vat, timeout=timeout)
        except Exception:
            _logger.warning('Failed VIES VAT check.', exc_info=True)
            return {}

        if not vies_result or not vies_result.get('valid') or vies_result.get('name') == '---':
            return {}

        address = list(filter(bool, (vies_result.get('address') or '').split('\n')))
        street = address[0] if address else False
        zip_city_record = next((line for line in address[1:] if re.match(r'^\d', line)), None)
        zip_city = zip_city_record.split(' ', 1) if zip_city_record else [False, False]
        street2 = next((line for line in address[1:] if line != zip_city_record), False)

        return self._iap_replace_location_codes({
            'name': vies_result.get('name'),
            'vat': vies_vat,
            'street': street,
            'street2': street2,
            'city': zip_city[1] if len(zip_city) > 1 else False,
            'zip': zip_city[0],
            'country_code': vies_result.get('countryCode') or vies_vat[:2],
            'duns': False,
            'email': False,
            'phone': False,
            'website': False,
            'domain': False,
            'logo': False,
            'unspsc_codes': [],
        })

    @api.model
    def _prepare_vies_vat(self, vat, query_country_code=False):
        sanitized_vat = re.sub(r'[^A-Za-z0-9]', '', vat or '').upper()
        if not sanitized_vat:
            return False
        country_code = sanitized_vat[:2] if sanitized_vat[:2].isalpha() else (query_country_code or '').upper()
        if country_code not in EU_VAT_COUNTRY_CODES:
            return False
        if not sanitized_vat[:2].isalpha():
            sanitized_vat = f'{country_code}{sanitized_vat}'
        return sanitized_vat
