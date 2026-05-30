# -*- coding: utf-8 -*-

import re

from odoo import api, models
from odoo.fields import Domain
from odoo.tools.mail import email_domain_extract, url_domain_extract


LOCAL_DUNS_PREFIX = 'local:'
SEARCH_FIELDS = (
    'name',
    'complete_name',
    'commercial_company_name',
    'email',
    'phone',
    'mobile',
    'website',
    'vat',
)


class IapAutocompleteApi(models.AbstractModel):
    _inherit = 'iap.autocomplete.api'

    @api.model
    def _request_partner_autocomplete(self, action, params, timeout=15):
        params = params or {}
        if action in ('search_by_name', 'search_by_vat'):
            query = params.get('query') or ''
            partners = self._local_partner_search(
                query,
                query_country_code=params.get('query_country_code'),
                search_vat=action == 'search_by_vat',
            )
            return self._autocomplete_response([
                self._partner_to_autocomplete_data(partner)
                for partner in partners
            ]), False

        if action == 'enrich_by_duns':
            partner = self._partner_from_local_token(params.get('duns'))
            return self._autocomplete_response(
                self._partner_to_autocomplete_data(partner) if partner else {}
            ), False

        if action == 'enrich_by_gst':
            partners = self._local_partner_search(params.get('gst') or '', search_vat=True, limit=1)
            partner = partners[:1]
            return self._autocomplete_response(
                self._partner_to_autocomplete_data(partner) if partner else {}
            ), False

        if action == 'enrich_by_domain':
            partner = self._local_partner_from_domain(params.get('domain'))
            return self._autocomplete_response(
                self._partner_to_autocomplete_data(partner) if partner else {}
            ), False

        return self._autocomplete_response({} if action.startswith('enrich_by_') else []), False

    @api.model
    def _autocomplete_response(self, data):
        return {
            'data': data,
            'error': False,
            'credit_error': False,
        }

    @api.model
    def _local_partner_search(self, query, query_country_code=False, search_vat=False, limit=10):
        query = (query or '').strip()
        if not query:
            return self.env['res.partner']

        Partner = self.env['res.partner']
        domain = self._local_vat_domain(query) if search_vat else self._local_name_domain(query)
        if not domain:
            return Partner

        if query_country_code:
            country = self.env['res.country'].search([('code', '=ilike', query_country_code)], limit=1)
            if not country:
                return Partner
            domain = Domain.AND([domain, [
                '|',
                ('country_id', '=', country.id),
                ('country_id', '=', False),
            ]])

        partners = Partner.search(domain, limit=limit * 3, order='is_company desc, name')
        ranked_ids = [
            partner.id
            for partner in sorted(
                partners,
                key=lambda partner: self._partner_match_score(partner, query, search_vat),
            )
        ][:limit]
        return Partner.browse(ranked_ids)

    @api.model
    def _local_name_domain(self, query):
        Partner = self.env['res.partner']
        fields = [field for field in SEARCH_FIELDS if field in Partner._fields]
        token_domains = []
        for token in re.findall(r'\w+', query):
            field_domains = [[(field, 'ilike', token)] for field in fields]
            if field_domains:
                token_domains.append(Domain.OR(field_domains))
        return Domain.AND(token_domains) if token_domains else []

    @api.model
    def _local_vat_domain(self, query):
        candidates = {query, self._normalize_identifier(query)}
        normalized = self._normalize_identifier(query)
        if len(normalized) > 2 and normalized[:2].isalpha():
            candidates.add(normalized[2:])
        candidates = {candidate for candidate in candidates if candidate}
        if not candidates:
            return []
        return Domain.OR([
            [('vat', 'ilike', candidate)]
            for candidate in candidates
        ])

    @api.model
    def _partner_match_score(self, partner, query, search_vat=False):
        normalized_query = self._normalize_identifier(query)
        normalized_vat = self._normalize_identifier(partner.vat or '')
        name = (partner.name or '').lower()
        query_lower = (query or '').lower()

        if search_vat and normalized_query and normalized_query == normalized_vat:
            return (0, partner.name or '')
        if query_lower and name.startswith(query_lower):
            return (1, partner.name or '')
        if partner.is_company:
            return (2, partner.name or '')
        return (3, partner.name or '')

    @api.model
    def _partner_from_local_token(self, token):
        token = str(token or '')
        if not token.startswith(LOCAL_DUNS_PREFIX):
            return self.env['res.partner']

        try:
            partner_id = int(token.removeprefix(LOCAL_DUNS_PREFIX))
        except ValueError:
            return self.env['res.partner']
        return self.env['res.partner'].browse(partner_id).exists()

    @api.model
    def _local_partner_from_domain(self, domain):
        domain = (domain or '').strip().lower()
        if not domain:
            return self.env['res.partner']

        Partner = self.env['res.partner']
        candidates = Partner.search([
            '|',
            ('website', 'ilike', domain),
            ('email', 'ilike', '@' + domain),
        ], limit=20)
        for partner in candidates:
            partner_domain = self._partner_domain(partner)
            if partner_domain == domain:
                return partner
        return candidates[:1]

    @api.model
    def _partner_to_autocomplete_data(self, partner):
        if not partner:
            return {}

        return {
            'name': partner.commercial_company_name or partner.name or '',
            'duns': f'{LOCAL_DUNS_PREFIX}{partner.id}',
            'vat': partner.vat or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'zip': partner.zip or '',
            'country_code': partner.country_id.code or '',
            'country_name': partner.country_id.name or '',
            'state_code': partner.state_id.code or '',
            'state_name': partner.state_id.name or '',
            'email': partner.email or '',
            'phone': partner.phone or getattr(partner, 'mobile', False) or '',
            'website': partner.website or '',
            'domain': self._partner_domain(partner) or '',
            'logo': False,
            'unspsc_codes': [],
            'industry_code': False,
            'preferred_language': partner.lang or False,
        }

    @api.model
    def _partner_domain(self, partner):
        if partner.website:
            return (url_domain_extract(partner.website) or '').lower()
        if partner.email:
            return (email_domain_extract(partner.email) or '').lower()
        return ''

    @api.model
    def _normalize_identifier(self, value):
        return re.sub(r'[^A-Za-z0-9]', '', value or '').lower()
