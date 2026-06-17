# -*- coding: utf-8 -*-

import difflib
import json
import re

from lxml import etree
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html_sanitize, plaintext2html


BLOCKED_TAGS_RE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|applet|link|meta|base|form|input|textarea|select|button)\b[^>]*>",
    re.IGNORECASE,
)
BLOCKED_BLOCK_RE = re.compile(
    r"<\s*(script|iframe|object|embed|applet)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
EVENT_ATTR_RE = re.compile(r"\s+on[a-zA-Z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
EVENT_ATTR_UNQUOTED_RE = re.compile(r"\s+on[a-zA-Z]+\s*=\s*[^\s>]+", re.IGNORECASE)
JS_URL_RE = re.compile(r"(href|src)\s*=\s*(['\"])\s*javascript:.*?\2", re.IGNORECASE | re.DOTALL)
QWEB_ATTR_RE = re.compile(r"\s+t-[a-zA-Z0-9_-]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
QWEB_TAG_RE = re.compile(r"<\s*/?\s*t\b[^>]*>", re.IGNORECASE)
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
FENCE_RE = re.compile(r"^\s*```(?:json|html)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)
CSS_BAD_RE = re.compile(r"(@import|expression\s*\(|javascript:|behavior\s*:|url\s*\()", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_FRAGMENT_RE = re.compile(
    r"(<(?:section|div|main|article|header)\b[\s\S]*</(?:section|div|main|article|header)>)",
    re.IGNORECASE,
)
HTML_FENCE_RE = re.compile(r"```html\s*([\s\S]*?)```", re.IGNORECASE)
JSON_FENCE_RE = re.compile(r"```json\s*([\s\S]*?)```", re.IGNORECASE)


class ElsxWebsiteAiDraft(models.Model):
    _name = 'elsx.website.ai.draft'
    _description = 'ELSx AI Website Draft'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('AI Website Draft'))
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('page_created', 'Unpublished Page Created'),
        ('published', 'Published'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], default='draft', required=True, index=True)
    mode = fields.Selection([
        ('new_page', 'New Page'),
        ('improve_page', 'Improve Current Page'),
        ('add_section', 'Add Section'),
        ('seo', 'SEO Polish'),
        ('mobile', 'Mobile Fix Suggestions'),
        ('cta', 'CTA / Form Section'),
        ('crm_whatsapp', 'CRM / WhatsApp Landing Page'),
    ], default='new_page', required=True)
    edit_scope = fields.Selection([
        ('full_page', 'Full Page'),
        ('hero', 'Hero / First Fold'),
        ('section', 'Single Section'),
        ('copy', 'Copywriting Only'),
        ('layout', 'Layout / UX'),
        ('conversion', 'Conversion / CTA'),
        ('seo', 'SEO Structure'),
        ('mobile', 'Mobile Responsiveness'),
        ('brand_system', 'Brand System'),
    ], default='full_page', required=True)
    apply_strategy = fields.Selection([
        ('new_unpublished', 'Create New Unpublished Page'),
        ('improved_copy', 'Create Improved Copy of Existing Page'),
        ('section_draft', 'Create Reusable Section Draft'),
    ], default='new_unpublished', required=True)
    section_position = fields.Selection([
        ('auto', 'AI Decide'),
        ('top', 'Top of Page'),
        ('after_hero', 'After Hero'),
        ('middle', 'Middle Content'),
        ('before_footer', 'Before Footer / Final CTA'),
    ], default='auto')
    design_style = fields.Selection([
        ('enterprise', 'Enterprise SaaS'),
        ('premium_industrial', 'Premium Industrial'),
        ('clean_b2b', 'Clean B2B'),
        ('conversion', 'Conversion Landing Page'),
        ('editorial', 'Editorial / Story'),
        ('minimal', 'Minimal'),
        ('bold', 'Bold Modern'),
    ], default='enterprise', required=True)
    page_blueprint = fields.Selection([
        ('auto', 'AI Decide'),
        ('homepage', 'Homepage'),
        ('landing', 'Campaign / Landing Page'),
        ('product', 'Product / Category Page'),
        ('service', 'Service Page'),
        ('quote', 'Quote Enquiry Page'),
        ('catalogue', 'Catalogue / Downloads Page'),
        ('about', 'About / Trust Page'),
        ('contact', 'Contact / Lead Capture Page'),
        ('seo_cluster', 'SEO Topic Page'),
    ], default='auto', required=True)
    device_focus = fields.Selection([
        ('all', 'All Devices'),
        ('desktop', 'Desktop First'),
        ('tablet', 'Tablet First'),
        ('mobile', 'Mobile First'),
    ], default='all', required=True)
    content_depth = fields.Selection([
        ('compact', 'Compact'),
        ('balanced', 'Balanced'),
        ('detailed', 'Detailed'),
    ], default='balanced', required=True)
    instruction = fields.Text(required=True)
    revision_notes = fields.Text(
        string='Revision / Follow-up Command',
        help='Use this to ask for precise changes after the first draft, for example: make hero stronger, add dealer CTA, simplify mobile layout.',
    )
    business_context = fields.Text(
        string='Business Context',
        help='Brand, products, services, geography, compliance notes, and important business facts the AI should respect.',
    )
    target_audience = fields.Char(help='Example: dealers, B2B buyers, students, parents, procurement teams.')
    page_goal = fields.Char(help='Example: collect quote requests, explain product range, improve trust, increase form submissions.')
    brand_tone = fields.Selection([
        ('professional', 'Professional'),
        ('premium', 'Premium'),
        ('technical', 'Technical'),
        ('friendly', 'Friendly'),
        ('direct', 'Direct'),
    ], default='professional')
    requested_url = fields.Char(
        string='Requested URL',
        help='Optional. Example: /frp-manhole-covers. The system will still make it unique and unpublished first.',
    )
    asset_guidance = fields.Text(
        string='Image / Asset Guidance',
        help='Describe preferred visuals, product categories, trust badges, catalogue links, or assets to reference. No external scripts are allowed.',
    )
    asset_strategy = fields.Selection([
        ('odoo_first', 'Use Odoo Media First'),
        ('product_first', 'Use Product Images First'),
        ('brand_first', 'Use Brand Assets First'),
        ('no_images', 'No Images'),
    ], default='odoo_first', required=True)
    asset_intents = fields.Text(readonly=True)
    asset_candidates = fields.Text(readonly=True)
    conversion_action = fields.Selection([
        ('quote', 'Request Quote'),
        ('contact', 'Contact / Callback'),
        ('catalogue', 'Download / View Catalogue'),
        ('whatsapp', 'WhatsApp Enquiry'),
        ('shop', 'Shop / Product Page'),
        ('form', 'Lead Form'),
        ('none', 'No Primary CTA'),
    ], default='quote')
    website_id = fields.Many2one('website', default=lambda self: self._default_website_id(), ondelete='set null')
    source_page_id = fields.Many2one('website.page', string='Source Page', ondelete='set null')
    target_page_id = fields.Many2one('website.page', string='Unpublished Draft Page', readonly=True, ondelete='set null')
    target_page_published = fields.Boolean(related='target_page_id.is_published', string='Published', readonly=True)
    provider_id = fields.Many2one('elsx.ai.provider', readonly=True, ondelete='set null')
    ai_job_id = fields.Many2one('elsx.ai.job', readonly=True, ondelete='set null')
    original_arch = fields.Text(readonly=True)
    raw_ai_output = fields.Text(readonly=True)
    ai_summary = fields.Text(readonly=True)
    studio_brief = fields.Text(compute='_compute_studio_brief')
    section_plan = fields.Text(readonly=True)
    quality_score = fields.Integer(readonly=True)
    quality_checklist = fields.Text(readonly=True)
    draft_html = fields.Text(readonly=True)
    draft_css = fields.Text(readonly=True)
    draft_preview_html = fields.Html(compute='_compute_draft_preview_html', sanitize=False)
    seo_title = fields.Char(readonly=True)
    seo_description = fields.Text(readonly=True)
    seo_keywords = fields.Char(readonly=True)
    warnings = fields.Text(readonly=True)
    diff_text = fields.Text(compute='_compute_diff_text')
    preview_url = fields.Char(compute='_compute_preview_url')
    published_by_id = fields.Many2one('res.users', readonly=True, ondelete='set null')
    published_date = fields.Datetime(readonly=True)
    version_ids = fields.One2many('elsx.website.ai.version', 'draft_id', readonly=True)

    @api.model
    def _default_website_id(self):
        try:
            return self.env['website'].get_current_website()
        except Exception:
            return self.env['website'].search([], limit=1)

    def _check_manager(self):
        if not self.env.user.has_group('elsx_ai_website_builder.group_ai_website_builder_manager'):
            raise AccessError(_("Only ELSx AI Studio managers can generate or apply website drafts."))

    @api.depends('target_page_id', 'target_page_id.url')
    def _compute_preview_url(self):
        for draft in self:
            draft.preview_url = draft.target_page_id.url if draft.target_page_id else False

    @api.depends('draft_html', 'draft_css')
    def _compute_draft_preview_html(self):
        for draft in self:
            if not draft.draft_html:
                draft.draft_preview_html = False
                continue
            css = draft._sanitize_css(draft.draft_css or '')
            style = '<style>%s</style>' % escape(css) if css else ''
            draft.draft_preview_html = Markup(
                '<div class="o_elsx_ai_preview_shell">%s<div class="o_elsx_ai_preview_body">%s</div></div>'
            ) % (Markup(style), Markup(draft.draft_html))

    @api.depends('original_arch', 'draft_html', 'draft_css', 'seo_title')
    def _compute_diff_text(self):
        for draft in self:
            if not draft.original_arch or not draft.draft_html:
                draft.diff_text = False
                continue
            new_arch = draft._build_page_arch(
                draft.seo_title or draft.name,
                draft.draft_html,
                draft.draft_css or '',
                'website.ai_preview',
            )
            diff = difflib.unified_diff(
                (draft.original_arch or '').splitlines(),
                (new_arch or '').splitlines(),
                fromfile='current_page',
                tofile='ai_draft_copy',
                lineterm='',
            )
            draft.diff_text = '\n'.join(diff)

    @api.onchange('source_page_id')
    def _onchange_source_page_id(self):
        if self.source_page_id and (not self.name or self.name == _('AI Website Draft')):
            self.name = _('AI improvement: %s') % self.source_page_id.name
        if self.source_page_id and self.apply_strategy == 'new_unpublished':
            self.apply_strategy = 'improved_copy'

    @api.depends(
        'mode', 'edit_scope', 'apply_strategy', 'section_position', 'design_style',
        'page_blueprint', 'device_focus', 'content_depth', 'conversion_action', 'source_page_id',
        'requested_url', 'revision_notes'
    )
    def _compute_studio_brief(self):
        for draft in self:
            chunks = [
                _('Mode: %s') % dict(draft._fields['mode'].selection).get(draft.mode, draft.mode),
                _('Scope: %s') % dict(draft._fields['edit_scope'].selection).get(draft.edit_scope, draft.edit_scope),
                _('Strategy: %s') % dict(draft._fields['apply_strategy'].selection).get(draft.apply_strategy, draft.apply_strategy),
                _('Blueprint: %s') % dict(draft._fields['page_blueprint'].selection).get(draft.page_blueprint, draft.page_blueprint),
                _('Style: %s') % dict(draft._fields['design_style'].selection).get(draft.design_style, draft.design_style),
                _('Device focus: %s') % dict(draft._fields['device_focus'].selection).get(draft.device_focus, draft.device_focus),
                _('Depth: %s') % dict(draft._fields['content_depth'].selection).get(draft.content_depth, draft.content_depth),
                _('CTA: %s') % dict(draft._fields['conversion_action'].selection).get(draft.conversion_action, draft.conversion_action),
            ]
            if draft.section_position:
                chunks.append(_('Section placement: %s') % dict(draft._fields['section_position'].selection).get(draft.section_position, draft.section_position))
            if draft.source_page_id:
                chunks.append(_('Source page: %s') % draft.source_page_id.display_name)
            if draft.requested_url:
                chunks.append(_('Requested URL: %s') % draft.requested_url)
            if draft.revision_notes:
                chunks.append(_('Revision command: %s') % draft.revision_notes)
            draft.studio_brief = '\n'.join(chunks)

    def _build_prompt_text(self):
        self.ensure_one()
        source = ''
        if self.source_page_id:
            source = (self.source_page_id.arch or '')[:12000]
        mode_guides = {
            'new_page': 'Create a complete unpublished page structure with hero, proof points, body sections, CTA, and SEO.',
            'improve_page': 'Improve the supplied page by rewriting weak copy, improving structure, CTA clarity, trust signals, and mobile readability.',
            'add_section': 'Create one polished section that can be reviewed and added to a copy of the source page.',
            'seo': 'Focus on SEO title, description, headings, concise copy, and internal CTA clarity.',
            'mobile': 'Focus on responsive section structure, concise headings, touch-friendly CTA layout, and no overflow.',
            'cta': 'Create conversion-focused CTA/form-supporting content without raw form fields or credential capture.',
            'crm_whatsapp': 'Create a lead-generation page that connects website visitors to CRM qualification, WhatsApp enquiry, quote request, and human handoff.',
        }
        scope_guides = {
            'full_page': 'Return a complete page body with multiple sections and a final conversion CTA.',
            'hero': 'Focus on a first-viewport hero: clear headline, proof, CTA, and a hint of following content.',
            'section': 'Return a self-contained section that can be inserted into an existing page copy.',
            'copy': 'Improve wording and hierarchy while keeping markup conservative.',
            'layout': 'Improve scanability, spacing, responsive grids, and content order.',
            'conversion': 'Strengthen trust, objections, CTA, lead capture flow, and decision clarity.',
            'seo': 'Strengthen semantic headings, topic coverage, title, and description.',
            'mobile': 'Prioritize touch spacing, short headings, no horizontal overflow, and stacked sections.',
            'brand_system': 'Create reusable brand-aligned section patterns, colors, typography guidance, and CTA style.',
        }
        style_guides = {
            'enterprise': 'Quiet, polished, high-trust SaaS/business interface, not decorative marketing clutter.',
            'premium_industrial': 'Strong industrial credibility with product confidence, certifications, logistics, and B2B trust.',
            'clean_b2b': 'Clear B2B sales page with dense but readable proof and straightforward CTA.',
            'conversion': 'Landing-page flow optimized for lead capture and WhatsApp/contact actions.',
            'editorial': 'Narrative structure with readable long-form sections and proof.',
            'minimal': 'Simple clean sections with restrained visual hierarchy.',
            'bold': 'Modern assertive layout with strong headings and confident CTAs.',
        }
        blueprint_guides = {
            'auto': 'Choose the strongest page architecture for the command and explain the section plan in the summary.',
            'homepage': 'Create a homepage with clear positioning, service/product paths, proof, and final CTA.',
            'landing': 'Create a campaign landing page with a sharp offer, objections, proof, urgency, and conversion CTA.',
            'product': 'Create a product/category page with use cases, specifications, benefits, proof, and enquiry path.',
            'service': 'Create a service page with problems solved, process, deliverables, proof, and contact CTA.',
            'quote': 'Create a quote enquiry page that prepares buyers to share requirements and request pricing.',
            'catalogue': 'Create a catalogue/download page with product categories, value, and catalogue CTA.',
            'about': 'Create a trust page with story, capabilities, proof, team/process confidence, and enquiry CTA.',
            'contact': 'Create a contact/lead-capture page with reasons to contact, contact paths, and next steps.',
            'seo_cluster': 'Create an SEO topic page with useful sections, FAQ-style answers, and internal CTA structure.',
        }
        return _(
            "Build a safe Odoo website draft.\n"
            "Mode: %(mode)s\n"
            "Mode guide: %(mode_guide)s\n"
            "Edit scope: %(edit_scope)s\n"
            "Scope guide: %(scope_guide)s\n"
            "Apply strategy: %(apply_strategy)s\n"
            "Section placement: %(section_position)s\n"
            "Page blueprint: %(page_blueprint)s\n"
            "Blueprint guide: %(blueprint_guide)s\n"
            "Design style: %(design_style)s\n"
            "Style guide: %(style_guide)s\n"
            "Device focus: %(device_focus)s\n"
            "Content depth: %(content_depth)s\n"
            "Primary conversion action: %(conversion_action)s\n"
            "Instruction: %(instruction)s\n"
            "Revision/follow-up command: %(revision_notes)s\n"
            "Business context: %(business_context)s\n"
            "Image/asset guidance: %(asset_guidance)s\n"
            "Available Odoo asset candidates: %(asset_candidates)s\n"
            "Target audience: %(target_audience)s\n"
            "Page goal: %(page_goal)s\n"
            "Brand tone: %(brand_tone)s\n"
            "Requested URL: %(requested_url)s\n"
            "Return ONLY JSON with keys: summary, html, css, seo_title, seo_description, seo_keywords, image_intents, warnings, section_plan.\n"
            "The summary must include a concise section plan and why each section exists. "
            "image_intents must list visual needs for the page, for example product close-up, factory, catalogue, support desk, trust proof, and CTA background. "
            "HTML must be clean Bootstrap/Odoo website section markup only. Prefer Odoo core snippet structures and classes such as "
            "s_cover, s_text_block, s_text_image, s_features_grid, s_numbers_grid, s_call_to_action, s_faq_collapse, "
            "container, row, col-lg-*, card, lead, badge, and btn. No scripts, iframes, forms, inputs, QWeb t-tags, "
            "inline event handlers, external JS, tracking pixels, credential capture, or Python/QWeb logic.\n"
            "Use <a class='btn'> for CTAs, not <button>. Use Odoo/Bootstrap-friendly section classes, containers, rows, columns, cards, badges, and responsive utilities.\n"
            "Build full pages as native editable sections, not one paragraph and not placeholder text. Full pages should normally include 6-9 sections: "
            "hero, trust/proof, product or service grid, process, comparison or objections, social proof, FAQ/answers, and final CTA. "
            "Every section must have a business purpose and editable text. Do not mention that the page was generated by AI. "
            "Keep it production-ready, easy to edit in Odoo Website, visually premium, mobile-safe, and free of generic filler.\n"
            "Source page XML, if any:\n%(source)s"
        ) % {
            'mode': dict(self._fields['mode'].selection).get(self.mode, self.mode),
            'mode_guide': mode_guides.get(self.mode, ''),
            'edit_scope': dict(self._fields['edit_scope'].selection).get(self.edit_scope, self.edit_scope),
            'scope_guide': scope_guides.get(self.edit_scope, ''),
            'apply_strategy': dict(self._fields['apply_strategy'].selection).get(self.apply_strategy, self.apply_strategy),
            'section_position': dict(self._fields['section_position'].selection).get(self.section_position, self.section_position),
            'page_blueprint': dict(self._fields['page_blueprint'].selection).get(self.page_blueprint, self.page_blueprint),
            'blueprint_guide': blueprint_guides.get(self.page_blueprint, ''),
            'design_style': dict(self._fields['design_style'].selection).get(self.design_style, self.design_style),
            'style_guide': style_guides.get(self.design_style, ''),
            'device_focus': dict(self._fields['device_focus'].selection).get(self.device_focus, self.device_focus),
            'content_depth': dict(self._fields['content_depth'].selection).get(self.content_depth, self.content_depth),
            'conversion_action': dict(self._fields['conversion_action'].selection).get(self.conversion_action, self.conversion_action),
            'instruction': self.instruction,
            'revision_notes': self.revision_notes or '',
            'business_context': self.business_context or '',
            'asset_guidance': self.asset_guidance or '',
            'asset_candidates': self._asset_candidate_text(),
            'target_audience': self.target_audience or '',
            'page_goal': self.page_goal or '',
            'brand_tone': dict(self._fields['brand_tone'].selection).get(self.brand_tone, self.brand_tone),
            'requested_url': self.requested_url or '',
            'source': source,
        }

    def _plain_text(self, value):
        text = HTML_TAG_RE.sub(' ', value or '')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _trim_sentence(self, text, limit=130):
        text = self._plain_text(text)
        if len(text) <= limit:
            return text
        cut = text[:limit].rsplit(' ', 1)[0].strip()
        return '%s...' % cut if cut else text[:limit]

    def _html_has_real_content(self, html):
        text = self._plain_text(html)
        if not text:
            return False
        failure_texts = (
            'ai output was empty after safety cleanup',
            'no content generated',
        )
        return not any(marker in text.lower() for marker in failure_texts)

    def _json_loads_relaxed(self, text):
        cleaned = (text or '').strip()
        if not cleaned:
            return {}
        json_match = JSON_FENCE_RE.search(cleaned)
        if json_match:
            cleaned = json_match.group(1).strip()
        cleaned = FENCE_RE.sub('', cleaned).strip()
        try:
            payload = json.loads(cleaned)
        except Exception:
            first = cleaned.find('{')
            last = cleaned.rfind('}')
            if first >= 0 and last > first:
                try:
                    payload = json.loads(cleaned[first:last + 1])
                except Exception:
                    payload = {}
            else:
                payload = {}
        return payload if isinstance(payload, dict) else {}

    def _extract_html_fragment(self, text):
        text = text or ''
        html_match = HTML_FENCE_RE.search(text)
        if html_match:
            return html_match.group(1).strip()
        fragment_match = HTML_FRAGMENT_RE.search(text)
        if fragment_match:
            return fragment_match.group(1).strip()
        return ''

    def _cta_label(self):
        labels = {
            'quote': _('Request Quote'),
            'contact': _('Talk to Sales'),
            'catalogue': _('View Catalogue'),
            'whatsapp': _('WhatsApp Enquiry'),
            'shop': _('View Products'),
            'form': _('Submit Enquiry'),
            'none': _('Learn More'),
        }
        return labels.get(self.conversion_action, _('Request Quote'))

    def _secondary_cta_label(self):
        labels = {
            'quote': _('View Catalogue'),
            'contact': _('View Services'),
            'catalogue': _('Ask for Pricing'),
            'whatsapp': _('Request Quote'),
            'shop': _('Talk to Expert'),
            'form': _('Contact Team'),
            'none': _('Contact Us'),
        }
        return labels.get(self.conversion_action, _('Contact Us'))

    def _infer_page_title(self):
        for value in (self.seo_title, self.name, self.page_goal, self.instruction):
            title = self._trim_sentence(value, 72)
            if title:
                return title
        return _('AI Website Draft')

    def _headline_from_instruction(self):
        instruction = self._trim_sentence(self.instruction, 110)
        if not instruction:
            return _('Build a Better Website Experience')
        lowered = instruction.lower()
        prefixes = (
            'create ', 'build ', 'make ', 'design ', 'develop ', 'generate ',
            'improve ', 'add ', 'write ', 'prepare ',
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                instruction = instruction[len(prefix):].strip()
                break
        instruction = instruction[:1].upper() + instruction[1:] if instruction else instruction
        return instruction.rstrip('.')

    def _split_business_points(self):
        source = '\n'.join(filter(None, [
            self.business_context or '',
            self.asset_guidance or '',
            self.page_goal or '',
            self.target_audience or '',
        ]))
        raw_items = re.split(r'[\n;\u2022]+', source)
        points = []
        for item in raw_items:
            cleaned = self._trim_sentence(item, 95)
            if cleaned and cleaned.lower() not in {point.lower() for point in points}:
                points.append(cleaned)
            if len(points) >= 6:
                break
        if points:
            return points
        return [
            _('Clear product and service positioning'),
            _('Trust-building proof for serious buyers'),
            _('Fast enquiry path for qualified leads'),
            _('Mobile-friendly sections that are easy to scan'),
        ]

    def _brand_label(self):
        website = self.website_id or self._default_website_id()
        company = website.company_id if website and website.company_id else self.env.company
        return company.display_name or _('Your Company')

    def _registry_has_model(self, model_name):
        return model_name in self.env.registry

    def _image_search_terms(self):
        source = ' '.join(filter(None, [
            self.instruction or '',
            self.page_goal or '',
            self.business_context or '',
            self.asset_guidance or '',
            self.target_audience or '',
            dict(self._fields['page_blueprint'].selection).get(self.page_blueprint, self.page_blueprint),
        ])).lower()
        stop_words = {
            'with', 'from', 'into', 'this', 'that', 'page', 'website', 'draft', 'create',
            'build', 'make', 'design', 'section', 'landing', 'contact', 'quote', 'request',
            'mobile', 'desktop', 'business', 'company', 'service', 'services',
        }
        words = []
        for word in re.findall(r'[a-z0-9][a-z0-9-]{2,}', source):
            if word not in stop_words and word not in words:
                words.append(word)
            if len(words) >= 10:
                break
        defaults = {
            'product': ['product', 'catalogue', 'specification'],
            'catalogue': ['catalogue', 'product', 'download'],
            'quote': ['sales', 'requirement', 'pricing'],
            'contact': ['support', 'contact', 'team'],
            'about': ['factory', 'team', 'quality'],
            'homepage': ['brand', 'business', 'hero'],
        }
        for word in defaults.get(self.page_blueprint or 'auto', ['hero', 'product', 'team']):
            if word not in words:
                words.append(word)
        return words[:12]

    def _asset_candidates_data(self, limit=8):
        self.ensure_one()
        if self.asset_strategy == 'no_images':
            return []
        terms = self._image_search_terms()
        candidates = []
        seen = set()

        def add_candidate(kind, name, src, reason):
            if not src or src in seen:
                return
            seen.add(src)
            candidates.append({
                'kind': kind,
                'name': self._trim_sentence(name, 70),
                'src': src,
                'reason': self._trim_sentence(reason, 110),
            })

        company = self.website_id.company_id if self.website_id and self.website_id.company_id else self.env.company
        if self.asset_strategy in ('brand_first', 'odoo_first') and company and getattr(company, 'logo', False):
            add_candidate('brand', company.display_name, '/web/image/res.company/%s/logo' % company.id, _('Company logo / brand identity'))

        if self._registry_has_model('product.template') and self.asset_strategy in ('product_first', 'odoo_first'):
            Product = self.env['product.template'].sudo()
            for term in terms[:6]:
                products = Product.search([
                    ('image_1920', '!=', False),
                    '|',
                    ('name', 'ilike', term),
                    ('description_sale', 'ilike', term),
                ], limit=2)
                for product in products:
                    add_candidate(
                        'product',
                        product.display_name,
                        '/web/image/product.template/%s/image_1024' % product.id,
                        _('Matched product image for "%s"') % term,
                    )
                    if len(candidates) >= limit:
                        return candidates

        if self.asset_strategy in ('odoo_first', 'brand_first'):
            Attachment = self.env['ir.attachment'].sudo()
            attachment_domain = [
                ('type', '=', 'binary'),
                ('mimetype', 'ilike', 'image/'),
                ('res_model', 'in', ['website', 'website.page', 'ir.ui.view', 'product.template', 'res.company']),
            ]
            for term in terms[:6]:
                attachments = Attachment.search(
                    attachment_domain + [('name', 'ilike', term)],
                    order='write_date desc, id desc',
                    limit=2,
                )
                for attachment in attachments:
                    add_candidate(
                        'media',
                        attachment.name,
                        '/web/image/ir.attachment/%s/datas' % attachment.id,
                        _('Matched Odoo media for "%s"') % term,
                    )
                    if len(candidates) >= limit:
                        return candidates

        if not candidates and self._registry_has_model('product.template') and self.asset_strategy != 'no_images':
            for product in self.env['product.template'].sudo().search([('image_1920', '!=', False)], limit=3):
                add_candidate(
                    'product',
                    product.display_name,
                    '/web/image/product.template/%s/image_1024' % product.id,
                    _('Recent product image available in Odoo'),
                )
        return candidates[:limit]

    def _asset_candidate_text(self):
        candidates = self._asset_candidates_data()
        if not candidates:
            return _('No local image candidates found. Use clean editable image placeholders and describe desired visuals.')
        return '\n'.join(
            '%s: %s -> %s (%s)' % (item['kind'], item['name'], item['src'], item['reason'])
            for item in candidates
        )

    def _asset_intent_text(self, payload=False):
        intents = []
        if isinstance(payload, dict):
            raw = payload.get('image_intents') or []
            if isinstance(raw, str):
                intents.extend([chunk.strip() for chunk in re.split(r'[\n,;]+', raw) if chunk.strip()])
            elif isinstance(raw, list):
                intents.extend(str(item).strip() for item in raw if item)
        for term in self._image_search_terms()[:6]:
            if term not in {item.lower() for item in intents}:
                intents.append(term)
        return '\n'.join(intents[:10])

    def _asset_showcase_html(self, candidates=False):
        if self.asset_strategy == 'no_images':
            return (
                '<div class="elsx-ai-visual-placeholder">'
                '<span class="badge text-bg-light">No image mode</span>'
                '<h3 class="h4-fs">Visual space reserved</h3>'
                '<p>Add final imagery from the Odoo Website editor when ready.</p>'
                '</div>'
            )
        candidates = candidates if candidates is not False else self._asset_candidates_data(limit=4)
        if candidates:
            primary = candidates[0]
            thumbs = ''.join(
                '<div class="elsx-ai-thumb"><img src="%s" alt="%s"/><span>%s</span></div>' % (
                    escape(item['src']),
                    escape(item['name']),
                    escape(item['kind'].title()),
                )
                for item in candidates[1:4]
            )
            return (
                '<figure class="elsx-ai-visual-stack">'
                '<img src="%s" alt="%s" class="img-fluid rounded shadow-sm"/>'
                '<figcaption><strong>%s</strong><span>%s</span></figcaption>'
                '<div class="elsx-ai-thumbs">%s</div>'
                '</figure>'
            ) % (
                escape(primary['src']),
                escape(primary['name']),
                escape(primary['name']),
                escape(primary['reason']),
                thumbs,
            )
        return (
            '<div class="elsx-ai-visual-placeholder">'
            '<span class="badge text-bg-light">Image intent</span>'
            '<h3 class="h4-fs">%s</h3>'
            '<p>%s</p>'
            '</div>'
        ) % (
            escape(self._headline_from_instruction()),
            escape(_('No matching Odoo media was found. Add a product, catalogue, factory, team, or proof image from the Website editor.')),
        )

    def _inject_asset_showcase(self, html, candidates=False):
        if not html or self.asset_strategy == 'no_images':
            return html
        if re.search(r'<img\b', html, re.IGNORECASE):
            return html
        visual = self._asset_showcase_html(candidates)
        section = (
            '<section class="s_text_image pt64 pb64" data-name="ELSx AI Visual Proof">'
            '<div class="container"><div class="row align-items-center g-5">'
            '<div class="col-lg-6">%s</div>'
            '<div class="col-lg-6"><p class="text-uppercase small text-muted mb-2">Visual direction</p>'
            '<h2 class="h3-fs">%s</h2><p class="lead">%s</p></div>'
            '</div></div></section>'
        ) % (
            visual,
            escape(_('Use real Odoo media, not random placeholders')),
            escape(_('This draft reserves image space and links it to media already available in Odoo so the final page remains editable and production-safe.')),
        )
        hero_end = re.search(r'</section>', html, re.IGNORECASE)
        if hero_end:
            return html[:hero_end.end()] + section + html[hero_end.end():]
        return section + html

    def _blueprint_sections(self):
        base = {
            'homepage': [
                ('Positioning hero', 'State the business clearly, show the primary value, and give two action paths.'),
                ('Product/service paths', 'Let visitors self-select the area they need without reading everything.'),
                ('Trust proof', 'Show capabilities, service confidence, geography, and operational credibility.'),
                ('Process', 'Explain how enquiry, quotation, delivery, or service happens.'),
                ('Use cases', 'Map the offer to real buyer situations.'),
                ('Final CTA', 'Convert interested visitors into contact or quote requests.'),
            ],
            'landing': [
                ('Offer hero', 'Present the campaign offer and reason to act.'),
                ('Pain and fit', 'Show who this is for and why it matters.'),
                ('Proof grid', 'Add concrete reasons to trust the offer.'),
                ('Objection handling', 'Answer pricing, quality, delivery, and support concerns.'),
                ('FAQ answers', 'Resolve hesitation before the CTA.'),
                ('Final conversion CTA', 'Make the next step obvious.'),
            ],
            'product': [
                ('Product hero', 'Explain the product/category and who should use it.'),
                ('Application grid', 'Show common use cases and buying contexts.'),
                ('Specification proof', 'Highlight technical criteria, capacities, materials, or fit.'),
                ('Why choose this', 'Compare with alternatives and surface differentiators.'),
                ('Buying process', 'Explain quotation, customization, delivery, and support.'),
                ('Catalogue/quote CTA', 'Offer catalogue and quote actions.'),
            ],
            'service': [
                ('Service hero', 'Define the service and outcome.'),
                ('Problems solved', 'Show the pain points the service removes.'),
                ('Delivery process', 'Explain assessment, execution, review, and support.'),
                ('Capabilities', 'Show tools, experience, and service coverage.'),
                ('Results and proof', 'Build confidence before contact.'),
                ('Consultation CTA', 'Invite the next action.'),
            ],
            'quote': [
                ('Quote request hero', 'Tell buyers exactly what information to share.'),
                ('Requirement checklist', 'List product, size, quantity, city, deadline, and documents.'),
                ('Buyer confidence', 'Explain response time and review process.'),
                ('Product fit grid', 'Help visitors choose what to quote.'),
                ('Next steps', 'Explain what happens after enquiry.'),
                ('Quote CTA', 'Send visitor to contact/form/WhatsApp.'),
            ],
            'catalogue': [
                ('Catalogue hero', 'Explain what the catalogue contains and who needs it.'),
                ('Category overview', 'Show product groups or content sections.'),
                ('Selection guide', 'Help buyers choose product fit.'),
                ('Proof and support', 'Mention technical help, quotes, and custom requirements.'),
                ('Download/view CTA', 'Make catalogue access clear.'),
                ('Sales handoff', 'Offer quote/contact after catalogue.'),
            ],
            'about': [
                ('Trust hero', 'Position the company and reason to believe.'),
                ('Capabilities', 'Show manufacturing/service/business strengths.'),
                ('Quality approach', 'Explain process, standards, and support.'),
                ('Customer fit', 'Show who the company serves.'),
                ('Timeline or values', 'Make the story concrete.'),
                ('Contact CTA', 'Turn trust into enquiry.'),
            ],
            'contact': [
                ('Contact hero', 'Tell visitors how and why to reach out.'),
                ('Contact paths', 'Offer sales, support, quote, and catalogue routes.'),
                ('Information checklist', 'Tell visitors what to include.'),
                ('Response promise', 'Set expectations for reply and next steps.'),
                ('Location/service area', 'Clarify business coverage.'),
                ('Final CTA', 'Repeat the main contact route.'),
            ],
            'seo_cluster': [
                ('Topic hero', 'Answer the main search intent directly.'),
                ('Core explanation', 'Teach the topic with useful, structured content.'),
                ('Use cases', 'Connect the topic to practical buying situations.'),
                ('Comparison/criteria', 'Help users evaluate options.'),
                ('FAQ answers', 'Cover related questions naturally.'),
                ('Conversion CTA', 'Offer quote/contact/catalogue after education.'),
            ],
            'auto': [
                ('First fold', 'Make the offer, audience, and next action obvious.'),
                ('Business proof', 'Show reasons to trust the business.'),
                ('Offer structure', 'Break services/products into scannable choices.'),
                ('Decision support', 'Answer important questions and objections.'),
                ('Action path', 'Guide visitors to enquiry, quote, catalogue, or contact.'),
                ('Final CTA', 'Repeat the main action clearly.'),
            ],
        }
        return base.get(self.page_blueprint or 'auto', base['auto'])

    def _build_section_plan_text(self):
        return '\n'.join(
            '%02d. %s - %s' % (idx + 1, title, purpose)
            for idx, (title, purpose) in enumerate(self._blueprint_sections())
        )

    def _quality_report(self, html, css, seo_title=False, seo_description=False):
        html = html or ''
        text = self._plain_text(html)
        section_count = len(re.findall(r'<section\b', html, re.IGNORECASE))
        h2_count = len(re.findall(r'<h2\b', html, re.IGNORECASE))
        cta_count = len(re.findall(r'<a\b[^>]*class=[\'"][^\'"]*btn', html, re.IGNORECASE))
        image_count = len(re.findall(r'<img\b', html, re.IGNORECASE))
        score = 0
        checks = []

        def add(label, passed, points):
            nonlocal score
            if passed:
                score += points
                checks.append('OK - %s' % label)
            else:
                checks.append('Needs work - %s' % label)

        add('6+ editable sections', section_count >= 6, 16)
        add('Strong heading structure', bool(re.search(r'<h1\b', html, re.IGNORECASE)) and h2_count >= 3, 13)
        add('Real content depth', len(text) >= 1100, 13)
        add('Visible CTA buttons', cta_count >= 2, 11)
        add('Responsive Odoo grid classes', 'container' in html and 'row' in html and 'col-' in html, 11)
        add('Image/media direction present', image_count >= 1 or 'elsx-ai-visual-placeholder' in html, 10)
        add('SEO metadata present', bool(seo_title) and bool(seo_description), 9)
        add('Business-specific language', len(set(re.findall(r'[A-Za-z][A-Za-z0-9-]{5,}', text))) >= 28, 9)
        add('No unsafe script/form tags', not BLOCKED_TAGS_RE.search(html) and not BLOCKED_BLOCK_RE.search(html), 10)
        add('No placeholder/empty-output language', 'ai output was empty' not in text.lower() and 'lorem ipsum' not in text.lower(), 8)

        return min(score, 100), '\n'.join(checks)

    def _build_local_payload(self, reason=False):
        self.ensure_one()
        title = self._infer_page_title()
        headline = self._headline_from_instruction()
        audience = self.target_audience or _('customers and decision makers')
        goal = self.page_goal or _('turn visitors into qualified enquiries')
        tone = dict(self._fields['brand_tone'].selection).get(self.brand_tone, self.brand_tone)
        design = dict(self._fields['design_style'].selection).get(self.design_style, self.design_style)
        device = dict(self._fields['device_focus'].selection).get(self.device_focus, self.device_focus)
        brand = self._brand_label()
        points = self._split_business_points()
        section_plan = self._build_section_plan_text()
        blueprint_sections = self._blueprint_sections()
        primary_cta = self._cta_label()
        secondary_cta = self._secondary_cta_label()
        card_html = ''.join(
            '<div class="col-lg-4 col-md-6">'
            '<div class="elsx-ai-card h-100">'
            '<span class="elsx-ai-card-index">%02d</span>'
            '<h3>%s</h3>'
            '<p>%s</p>'
            '</div>'
            '</div>' % (
                idx + 1,
                escape(point),
                escape('Designed to support %s with practical, editable website content.' % goal),
            )
            for idx, point in enumerate(points[:6])
        )
        blueprint_card_html = ''.join(
            '<div class="col-lg-4 col-md-6">'
            '<div class="elsx-ai-blueprint-card h-100">'
            '<span class="elsx-ai-card-index">%02d</span>'
            '<h3>%s</h3>'
            '<p>%s</p>'
            '</div>'
            '</div>' % (
                idx + 1,
                escape(item_title),
                escape(item_purpose),
            )
            for idx, (item_title, item_purpose) in enumerate(blueprint_sections[:6])
        )
        proof_items = [
            ('Draft-first', 'Create unpublished working copies before anything goes live.'),
            ('Editor-ready', 'Use Odoo Website sections, rows, cards, and CTA links that can be edited manually.'),
            ('Conversion-aware', 'Shape the page around enquiry, catalogue, quote, contact, or product actions.'),
            ('Mobile-safe', 'Keep sections stacked, readable, and touch-friendly across devices.'),
        ]
        proof_html = ''.join(
            '<div class="col-lg-3 col-sm-6"><div class="elsx-ai-proof h-100">'
            '<strong>%s</strong><span>%s</span></div></div>' % (escape(label), escape(body))
            for label, body in proof_items
        )
        faq_items = [
            ('What should this page make clear?', 'The visitor should understand the offer, who it is for, why to trust it, and what to do next.'),
            ('How is production protected?', 'The page is created as an unpublished copy first. A manager reviews, edits, and publishes manually.'),
            ('Can the design be changed later?', 'Yes. The output uses editable Odoo Website sections instead of locked custom scripts.'),
        ]
        faq_html = ''.join(
            '<div class="col-lg-4"><div class="elsx-ai-faq h-100">'
            '<h3 class="h5-fs">%s</h3><p>%s</p></div></div>' % (escape(question), escape(answer))
            for question, answer in faq_items
        )
        html = """
<section class="s_cover o_cc o_cc5 pt128 pb128" data-name="ELSx Studio Cover">
  <div class="container">
    <div class="row align-items-center g-5 s_allow_columns">
      <div class="col-lg-7">
        <p class="mb-3"><span class="badge rounded-pill text-bg-light">%(brand)s</span> <span class="badge rounded-pill text-bg-light">%(design)s | %(tone)s</span></p>
        <h1 class="display-3">%(headline)s</h1>
        <p class="lead">%(lead)s</p>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <a href="/contactus" class="btn btn-primary btn-lg o_translate_inline">%(primary_cta)s</a>
          <a href="/shop" class="btn btn-outline-light btn-lg o_translate_inline">%(secondary_cta)s</a>
        </div>
      </div>
      <div class="col-lg-5">
        <div class="card border-0 shadow-sm text-dark">
          <div class="card-body p-4">
          <h2 class="h3-fs">%(goal_title)s</h2>
          <p>%(goal_text)s</p>
          <div class="row g-3">
            <div class="col-4"><strong class="d-block h4 mb-0">24/7</strong><span class="small text-muted">Online enquiry</span></div>
            <div class="col-4"><strong class="d-block h4 mb-0">3x</strong><span class="small text-muted">Clearer CTAs</span></div>
            <div class="col-4"><strong class="d-block h4 mb-0">100%%</strong><span class="small text-muted">Draft first</span></div>
          </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
<section class="s_numbers_grid o_cc o_cc2 pt40 pb40" data-name="ELSx Studio Trust Bar">
  <div class="container">
    <div class="row g-3">
      %(proof_html)s
    </div>
  </div>
</section>
<section class="s_features_grid pt64 pb64" data-name="ELSx Studio Features">
  <div class="container">
    <div class="row">
      <div class="col-lg-12 pb24">
        <h2 class="h3-fs">Built around the exact website command</h2>
        <p class="lead h5-fs">Editable Odoo sections with clear hierarchy, proof, and conversion actions.</p>
        <div class="s_hr pt24 pb24"><hr class="w-100 mx-auto"/></div>
      </div>
    </div>
    <div class="row g-4">
      %(card_html)s
    </div>
  </div>
</section>
<section class="s_features_grid o_cc o_cc1 pt64 pb64" data-name="ELSx Studio Blueprint">
  <div class="container">
    <div class="row align-items-end">
      <div class="col-lg-8">
        <p class="text-uppercase small text-muted mb-2">Page architecture</p>
        <h2 class="h3-fs">A full section plan, not a thin placeholder page</h2>
        <p class="lead h5-fs">Each section has a role: explain, prove, answer, and convert.</p>
      </div>
      <div class="col-lg-4 text-lg-end">
        <span class="badge text-bg-light">%(blueprint)s</span>
      </div>
    </div>
    <div class="row g-4 mt-2">
      %(blueprint_card_html)s
    </div>
  </div>
</section>
<section class="s_text_image pt64 pb64" data-name="ELSx Studio Decision Support">
  <div class="container">
    <div class="row align-items-center g-5">
      <div class="col-lg-6">
        <h2 class="h3-fs">Make the buyer confident before they contact you</h2>
        <p class="lead">The page should reduce confusion, answer practical questions, and make the next step feel natural.</p>
        <ul class="list-unstyled">
          <li class="mb-2">✓ Clear audience and outcome</li>
          <li class="mb-2">✓ Business proof and service/product fit</li>
          <li class="mb-2">✓ Quote/contact/catalogue path without hunting</li>
        </ul>
      </div>
      <div class="col-lg-6">
        <div class="elsx-ai-panel">
          <h3 class="h4-fs">Command interpreted as</h3>
          <p>%(goal_text)s</p>
          <p class="mb-0"><strong>Audience:</strong> %(audience)s</p>
        </div>
      </div>
    </div>
  </div>
</section>
<section class="s_numbers_grid o_cc o_cc2 pt64 pb64" data-name="ELSx Studio Process">
  <div class="container">
    <div class="row g-4">
      <div class="col-lg-4">
        <div class="p-4 h-100">
          <p class="h1-fs mb-2">01</p>
          <h3 class="h4-fs">Explain</h3>
          <p>Make the offer obvious within the first screen for %(audience)s.</p>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="p-4 h-100">
          <p class="h1-fs mb-2">02</p>
          <h3 class="h4-fs">Prove</h3>
          <p>Use concise proof points, service fit, and business context instead of generic filler.</p>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="p-4 h-100">
          <p class="h1-fs mb-2">03</p>
          <h3 class="h4-fs">Convert</h3>
          <p>Guide visitors to %(primary_cta)s with a clean, mobile-safe action path.</p>
        </div>
      </div>
    </div>
  </div>
</section>
<section class="s_faq_collapse pt64 pb64" data-name="ELSx Studio Answers">
  <div class="container">
    <div class="row">
      <div class="col-lg-12 pb24">
        <h2 class="h3-fs">Questions this page should answer</h2>
        <p class="lead h5-fs">Use these editable answer blocks to remove hesitation before the CTA.</p>
      </div>
    </div>
    <div class="row g-4">
      %(faq_html)s
    </div>
  </div>
</section>
<section class="s_call_to_action o_cc o_cc5 pt64 pb64" data-name="ELSx Studio CTA">
  <div class="container">
    <div class="row align-items-center">
      <div class="col-lg-9">
        <p class="mb-2"><span class="badge text-bg-light">Ready for manager review</span></p>
        <h2 class="h3-fs">Turn the page into a reviewed, editable business asset.</h2>
        <p>Open this copy in the Website editor, replace any generic copy with final business details, and publish only after approval.</p>
      </div>
      <div class="col-lg-3 text-lg-end">
        <a href="/contactus" class="btn btn-primary btn-lg o_translate_inline">%(primary_cta)s</a>
      </div>
    </div>
  </div>
</section>
""" % {
            'brand': escape(brand),
            'design': escape(design),
            'tone': escape(tone),
            'headline': escape(headline),
            'lead': escape(_('A production-safe, editable website draft for %s, focused on %s and optimized for %s.') % (audience, goal, device)),
            'primary_cta': escape(primary_cta),
            'secondary_cta': escape(secondary_cta),
            'goal_title': escape(_('Page Goal')),
            'goal_text': escape(goal),
            'card_html': card_html,
            'audience': escape(audience),
            'proof_html': proof_html,
            'blueprint': escape(dict(self._fields['page_blueprint'].selection).get(self.page_blueprint, self.page_blueprint)),
            'blueprint_card_html': blueprint_card_html,
            'faq_html': faq_html,
        }
        css = """
.s_cover[data-name="ELSx Studio Cover"] h1 { letter-spacing: 0; line-height: 1.04; }
.s_cover[data-name="ELSx Studio Cover"] .lead { max-width: 720px; }
.s_numbers_grid[data-name="ELSx Studio Trust Bar"] .elsx-ai-proof { border-left: 3px solid #0f766e; padding: 1rem 1rem 1rem 1.1rem; background: rgba(255,255,255,.72); border-radius: 8px; }
.s_numbers_grid[data-name="ELSx Studio Trust Bar"] .elsx-ai-proof strong { display: block; font-size: 1rem; }
.s_numbers_grid[data-name="ELSx Studio Trust Bar"] .elsx-ai-proof span { display: block; color: #475569; margin-top: .25rem; }
.s_features_grid[data-name="ELSx Studio Features"] .elsx-ai-card { border: 1px solid #d8e1e5; border-radius: 8px; background: #fff; padding: 1.5rem; box-shadow: 0 10px 26px rgba(15, 23, 42, .06); }
.s_features_grid[data-name="ELSx Studio Features"] .elsx-ai-card-index { color: #0f766e; font-weight: 800; }
.s_features_grid[data-name="ELSx Studio Features"] h3 { margin-top: .75rem; font-size: 1.18rem; }
.s_features_grid[data-name="ELSx Studio Blueprint"] .elsx-ai-blueprint-card { border: 1px solid #d8e1e5; border-radius: 8px; background: #fff; padding: 1.5rem; }
.s_text_image[data-name="ELSx Studio Decision Support"] .elsx-ai-panel { border: 1px solid #d8e1e5; border-radius: 8px; padding: 2rem; background: #f8fafc; }
.s_faq_collapse[data-name="ELSx Studio Answers"] .elsx-ai-faq { border-top: 3px solid #0f766e; padding: 1.5rem; background: #fff; box-shadow: 0 10px 26px rgba(15, 23, 42, .06); }
@media (max-width: 768px) {
  .s_cover[data-name="ELSx Studio Cover"] { padding-top: 3rem !important; padding-bottom: 3rem !important; }
  .s_cover[data-name="ELSx Studio Cover"] .d-flex { flex-direction: column; align-items: stretch; }
}
"""
        warning = reason or _('AI response was not usable, so ELSx generated a safe editable page from the command.')
        return {
            'summary': _('Safe website draft generated from the builder command.'),
            'html': html,
            'css': css,
            'section_plan': section_plan,
            'seo_title': title,
            'seo_description': self._trim_sentence(
                self.page_goal or self.instruction or _('Production-safe AI website draft ready for review.'),
                155,
            ),
            'seo_keywords': self._trim_sentence(
                ', '.join(filter(None, [self.target_audience, self.conversion_action, self.design_style])),
                255,
            ),
            'warnings': [warning],
        }

    def _build_local_payload(self, reason=False):
        """Business-aware fallback used when provider output is weak or unsafe.

        This intentionally shadows the older generic fallback above. Keeping the
        old body in place avoids a large risky deletion while making the runtime
        behavior use this stronger Odoo-editor-friendly page architecture.
        """
        self.ensure_one()
        title = self._infer_page_title()
        headline = self._headline_from_instruction()
        audience = self.target_audience or _('customers and decision makers')
        goal = self.page_goal or _('turn visitors into qualified enquiries')
        tone = dict(self._fields['brand_tone'].selection).get(self.brand_tone, self.brand_tone)
        design = dict(self._fields['design_style'].selection).get(self.design_style, self.design_style)
        device = dict(self._fields['device_focus'].selection).get(self.device_focus, self.device_focus)
        brand = self._brand_label()
        section_plan = self._build_section_plan_text()
        primary_cta = self._cta_label()
        secondary_cta = self._secondary_cta_label()
        candidates = self._asset_candidates_data(limit=4)
        visual_html = self._asset_showcase_html(candidates)

        points = self._split_business_points()
        offer_cards = ''.join(
            '<div class="col-lg-4 col-md-6"><div class="elsx-studio-card h-100">'
            '<span class="elsx-studio-index">%02d</span><h3>%s</h3>'
            '<p>%s</p><a href="/contactus" class="stretched-link">%s</a></div></div>' % (
                idx + 1,
                escape(point),
                escape(_('Explain the buyer need, business proof, product fit, and next action in language a real visitor can act on.')),
                escape(primary_cta),
            )
            for idx, point in enumerate(points[:6])
        )
        blueprint_cards = ''.join(
            '<div class="col-lg-4 col-md-6"><div class="elsx-studio-blueprint h-100">'
            '<span class="elsx-studio-index">%02d</span><h3>%s</h3><p>%s</p></div></div>' % (
                idx + 1,
                escape(item_title),
                escape(item_purpose),
            )
            for idx, (item_title, item_purpose) in enumerate(self._blueprint_sections()[:6])
        )
        proof_html = ''.join(
            '<div class="col-lg-3 col-sm-6"><div class="elsx-studio-proof h-100">'
            '<strong>%s</strong><span>%s</span></div></div>' % (escape(label), escape(body))
            for label, body in [
                (_('Draft-first'), _('Unpublished copy before anything goes live.')),
                (_('Editor-ready'), _('Odoo sections, rows, images, cards, and CTA links.')),
                (_('Conversion-aware'), _('Visitor path shaped around enquiry, quote, catalogue, or contact.')),
                (_('Mobile-safe'), _('Stacked, readable, touch-friendly sections.')),
            ]
        )
        faq_html = ''.join(
            '<div class="col-lg-4"><div class="elsx-studio-faq h-100">'
            '<h3 class="h5-fs">%s</h3><p>%s</p></div></div>' % (escape(question), escape(answer))
            for question, answer in [
                (_('What should this page make clear?'), _('The offer, who it is for, why to trust it, and what to do next.')),
                (_('How is production protected?'), _('A manager reviews an unpublished copy before publishing manually.')),
                (_('Can the design be changed later?'), _('Yes. The output stays editable in the standard Odoo Website editor.')),
            ]
        )

        html = """
<section class="s_cover o_cc o_cc5 pt128 pb128" data-name="ELSx Studio Hero">
  <div class="container">
    <div class="row align-items-center g-5 s_allow_columns">
      <div class="col-lg-7">
        <p class="mb-3"><span class="badge rounded-pill text-bg-light">%(brand)s</span> <span class="badge rounded-pill text-bg-light">%(design)s | %(tone)s</span></p>
        <h1 class="display-3">%(headline)s</h1>
        <p class="lead">%(lead)s</p>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <a href="/contactus" class="btn btn-primary btn-lg o_translate_inline">%(primary_cta)s</a>
          <a href="/shop" class="btn btn-outline-light btn-lg o_translate_inline">%(secondary_cta)s</a>
        </div>
      </div>
      <div class="col-lg-5">%(visual_html)s</div>
    </div>
  </div>
</section>
<section class="s_numbers_grid o_cc o_cc2 pt40 pb40" data-name="ELSx Studio Trust Bar">
  <div class="container"><div class="row g-3">%(proof_html)s</div></div>
</section>
<section class="s_features_grid pt64 pb64" data-name="ELSx Studio Offer Grid">
  <div class="container">
    <div class="row"><div class="col-lg-12 pb24">
      <h2 class="h3-fs">Built around the actual business command</h2>
      <p class="lead h5-fs">Editable blocks for offer clarity, buyer fit, proof, and next action.</p>
      <div class="s_hr pt24 pb24"><hr class="w-100 mx-auto"/></div>
    </div></div>
    <div class="row g-4">%(offer_cards)s</div>
  </div>
</section>
<section class="s_features_grid o_cc o_cc1 pt64 pb64" data-name="ELSx Studio Page Architecture">
  <div class="container">
    <div class="row align-items-end">
      <div class="col-lg-8">
        <p class="text-uppercase small text-muted mb-2">Page architecture</p>
        <h2 class="h3-fs">A complete section plan, not a placeholder page</h2>
        <p class="lead h5-fs">Each section has a role: explain, prove, answer, and convert.</p>
      </div>
      <div class="col-lg-4 text-lg-end"><span class="badge text-bg-light">%(blueprint)s</span></div>
    </div>
    <div class="row g-4 mt-2">%(blueprint_cards)s</div>
  </div>
</section>
<section class="s_text_image pt64 pb64" data-name="ELSx Studio Decision Support">
  <div class="container">
    <div class="row align-items-center g-5">
      <div class="col-lg-6">
        <h2 class="h3-fs">Make the buyer confident before they contact you</h2>
        <p class="lead">Reduce confusion, answer practical questions, and make the next step feel natural.</p>
        <ul class="list-unstyled">
          <li class="mb-2">Clear audience and outcome</li>
          <li class="mb-2">Business proof and service/product fit</li>
          <li class="mb-2">Quote/contact/catalogue path without hunting</li>
        </ul>
      </div>
      <div class="col-lg-6"><div class="elsx-studio-panel">
        <h3 class="h4-fs">Command interpreted as</h3>
        <p>%(goal_text)s</p>
        <p class="mb-0"><strong>Audience:</strong> %(audience)s</p>
      </div></div>
    </div>
  </div>
</section>
<section class="s_numbers_grid o_cc o_cc2 pt64 pb64" data-name="ELSx Studio Process">
  <div class="container"><div class="row g-4">
    <div class="col-lg-4"><div class="p-4 h-100"><p class="h1-fs mb-2">01</p><h3 class="h4-fs">Explain</h3><p>Make the offer obvious within the first screen for %(audience)s.</p></div></div>
    <div class="col-lg-4"><div class="p-4 h-100"><p class="h1-fs mb-2">02</p><h3 class="h4-fs">Prove</h3><p>Use proof points, service fit, real media, and business context instead of filler.</p></div></div>
    <div class="col-lg-4"><div class="p-4 h-100"><p class="h1-fs mb-2">03</p><h3 class="h4-fs">Convert</h3><p>Guide visitors to %(primary_cta)s with a clean, mobile-safe action path.</p></div></div>
  </div></div>
</section>
<section class="s_faq_collapse pt64 pb64" data-name="ELSx Studio Answers">
  <div class="container">
    <div class="row"><div class="col-lg-12 pb24"><h2 class="h3-fs">Questions this page should answer</h2><p class="lead h5-fs">Use these editable answer blocks to remove hesitation before the CTA.</p></div></div>
    <div class="row g-4">%(faq_html)s</div>
  </div>
</section>
<section class="s_call_to_action o_cc o_cc5 pt64 pb64" data-name="ELSx Studio CTA">
  <div class="container"><div class="row align-items-center">
    <div class="col-lg-9">
      <p class="mb-2"><span class="badge text-bg-light">Ready for manager review</span></p>
      <h2 class="h3-fs">Turn this into a reviewed, editable business page.</h2>
      <p>Open the copy in the Website editor, polish final business details, and publish only after approval.</p>
    </div>
    <div class="col-lg-3 text-lg-end"><a href="/contactus" class="btn btn-primary btn-lg o_translate_inline">%(primary_cta)s</a></div>
  </div></div>
</section>
""" % {
            'brand': escape(brand),
            'design': escape(design),
            'tone': escape(tone),
            'headline': escape(headline),
            'lead': escape(_('A production-safe, editable website draft for %s, focused on %s and optimized for %s.') % (audience, goal, device)),
            'primary_cta': escape(primary_cta),
            'secondary_cta': escape(secondary_cta),
            'visual_html': visual_html,
            'proof_html': proof_html,
            'offer_cards': offer_cards,
            'blueprint': escape(dict(self._fields['page_blueprint'].selection).get(self.page_blueprint, self.page_blueprint)),
            'blueprint_cards': blueprint_cards,
            'goal_text': escape(goal),
            'audience': escape(audience),
            'faq_html': faq_html,
        }
        css = """
.elsx-ai-visual-stack { background: #fff; border-radius: 8px; padding: 1rem; color: #17202a; }
.elsx-ai-visual-stack > img { width: 100%%; aspect-ratio: 4 / 3; object-fit: cover; }
.elsx-ai-visual-stack figcaption { display: flex; flex-direction: column; gap: .15rem; margin-top: .85rem; color: #334155; }
.elsx-ai-thumbs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem; margin-top: .85rem; }
.elsx-ai-thumb { display: flex; flex-direction: column; gap: .25rem; font-size: .75rem; color: #475569; }
.elsx-ai-thumb img { width: 100%%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; }
.elsx-ai-visual-placeholder { border: 1px dashed #94a3b8; border-radius: 8px; padding: 2rem; background: rgba(255,255,255,.9); color: #17202a; }
.s_cover[data-name="ELSx Studio Hero"] h1 { letter-spacing: 0; line-height: 1.04; }
.s_cover[data-name="ELSx Studio Hero"] .lead { max-width: 720px; }
.elsx-studio-proof { border-left: 3px solid #0f766e; padding: 1rem 1rem 1rem 1.1rem; background: rgba(255,255,255,.72); border-radius: 8px; }
.elsx-studio-proof strong { display: block; font-size: 1rem; }
.elsx-studio-proof span { display: block; color: #475569; margin-top: .25rem; }
.elsx-studio-card { position: relative; border: 1px solid #d8e1e5; border-radius: 8px; background: #fff; padding: 1.5rem; box-shadow: 0 10px 26px rgba(15, 23, 42, .06); }
.elsx-studio-index { color: #0f766e; font-weight: 800; }
.elsx-studio-card h3 { margin-top: .75rem; font-size: 1.18rem; }
.elsx-studio-blueprint { border: 1px solid #d8e1e5; border-radius: 8px; background: #fff; padding: 1.5rem; }
.elsx-studio-panel { border: 1px solid #d8e1e5; border-radius: 8px; padding: 2rem; background: #f8fafc; }
.elsx-studio-faq { border-top: 3px solid #0f766e; padding: 1.5rem; background: #fff; box-shadow: 0 10px 26px rgba(15, 23, 42, .06); }
@media (max-width: 768px) {
  .s_cover[data-name="ELSx Studio Hero"] { padding-top: 3rem !important; padding-bottom: 3rem !important; }
  .s_cover[data-name="ELSx Studio Hero"] .d-flex { flex-direction: column; align-items: stretch; }
  .elsx-ai-thumbs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""
        warning = reason or _('AI response was not usable, so ELSx generated a safe editable page from the command.')
        return {
            'summary': _('Safe website draft generated from the builder command.'),
            'html': html,
            'css': css,
            'section_plan': section_plan,
            'seo_title': title,
            'seo_description': self._trim_sentence(
                self.page_goal or self.instruction or _('Production-safe AI website draft ready for review.'),
                155,
            ),
            'seo_keywords': self._trim_sentence(
                ', '.join(filter(None, [self.target_audience, self.conversion_action, self.design_style])),
                255,
            ),
            'image_intents': self._image_search_terms(),
            'warnings': [warning],
        }

    def _parse_ai_output(self, text):
        cleaned = text or ''
        payload = self._json_loads_relaxed(cleaned)
        if not payload:
            html = self._extract_html_fragment(cleaned)
            if html:
                payload = {
                    'summary': _('AI returned HTML instead of JSON; it was extracted and sanitized.'),
                    'html': html,
                    'css': '',
                    'warnings': [_('AI did not return structured JSON.')],
                }
            elif self._plain_text(cleaned):
                payload = self._build_local_payload(_('AI returned plain text instead of editable website sections.'))
            else:
                payload = self._build_local_payload(_('AI returned an empty response.'))
        return payload

    def _sanitize_css(self, css):
        css = (css or '').strip()
        if not css:
            return ''
        css = CSS_BAD_RE.sub('', css)
        css = css.replace('<', '').replace('>', '')
        return css[:6000]

    def _sanitize_html(self, html):
        html = html or ''
        html = STYLE_BLOCK_RE.sub('', html)
        html = BLOCKED_BLOCK_RE.sub('', html)
        html = BLOCKED_TAGS_RE.sub('', html)
        html = EVENT_ATTR_RE.sub('', html)
        html = EVENT_ATTR_UNQUOTED_RE.sub('', html)
        html = JS_URL_RE.sub('', html)
        html = QWEB_ATTR_RE.sub('', html)
        html = QWEB_TAG_RE.sub('', html)
        html = html_sanitize(
            html,
            sanitize_tags=True,
            sanitize_attributes=True,
            sanitize_style=True,
            sanitize_form=True,
            strip_classes=False,
            output_method='xml',
        )
        html = BLOCKED_TAGS_RE.sub('', html)
        html = EVENT_ATTR_RE.sub('', html)
        html = EVENT_ATTR_UNQUOTED_RE.sub('', html)
        html = JS_URL_RE.sub('', html)
        html = QWEB_ATTR_RE.sub('', html)
        html = QWEB_TAG_RE.sub('', html)
        return html[:60000]

    def _safe_slug(self, title):
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', (title or 'ai-page').strip().lower()).strip('-')
        return (slug or 'ai-page')[:70]

    def _website_page_model_for_create(self, website):
        """Create website pages without leaking AI wizard defaults into ir.ui.view.

        The AI draft action context contains keys such as default_mode='new_page'.
        website.page delegates to ir.ui.view, whose technical mode field accepts
        only Odoo view modes. Keeping the page-create context clean prevents
        those AI defaults from becoming invalid ir.ui.view values.
        """
        clean_context = {
            key: value
            for key, value in self.env.context.items()
            if not key.startswith('default_')
        }
        clean_context.update({
            'website_id': website.id,
            'default_mode': 'primary',
        })
        return self.env['website.page'].sudo(False).with_context(clean_context)

    def _as_warning_text(self, warnings):
        if isinstance(warnings, list):
            return '\n'.join(str(item) for item in warnings if item)
        return warnings or ''

    def _detect_safety_warnings(self, raw_html, raw_css):
        warnings = []
        raw_html = raw_html or ''
        raw_css = raw_css or ''
        if BLOCKED_BLOCK_RE.search(raw_html) or BLOCKED_TAGS_RE.search(raw_html):
            warnings.append(_("Unsafe HTML tags were removed before preview."))
        if EVENT_ATTR_RE.search(raw_html) or EVENT_ATTR_UNQUOTED_RE.search(raw_html):
            warnings.append(_("Inline JavaScript event handlers were removed."))
        if JS_URL_RE.search(raw_html):
            warnings.append(_("JavaScript URLs were removed from links or media."))
        if QWEB_ATTR_RE.search(raw_html) or QWEB_TAG_RE.search(raw_html):
            warnings.append(_("QWeb directives were removed; AI output cannot execute framework logic."))
        if STYLE_BLOCK_RE.search(raw_html):
            warnings.append(_("Inline style blocks were moved out of HTML and sanitized."))
        if CSS_BAD_RE.search(raw_css):
            warnings.append(_("Unsafe CSS constructs were removed."))
        return warnings

    def _merge_warnings(self, ai_warnings, safety_warnings):
        chunks = []
        if ai_warnings:
            chunks.append(ai_warnings)
        if safety_warnings:
            chunks.append('\n'.join(str(item) for item in safety_warnings if item))
        return '\n'.join(chunk for chunk in chunks if chunk)

    def _build_page_arch(self, title, html, css, key):
        html = self._sanitize_html(html)
        css = self._sanitize_css(css)
        css_block = '\n<style>%s</style>' % escape(css) if css else ''
        arch = (
            '<t name="%s" t-name="%s">\n'
            '  <t t-call="website.layout">\n'
            '    <div id="wrap" class="oe_structure">\n'
            '%s%s\n'
            '    </div>\n'
            '  </t>\n'
            '</t>'
        ) % (escape(title or _('AI Website Draft')), escape(key), html, css_block)
        try:
            etree.fromstring(arch.encode('utf-8'))
        except Exception:
            safe_body = '<section class="s_text_block pt40 pb40"><div class="container">%s</div></section>' % plaintext2html(
                html, container_tag='div'
            )
            arch = (
                '<t name="%s" t-name="%s"><t t-call="website.layout">'
                '<div id="wrap" class="oe_structure">%s</div></t></t>'
            ) % (escape(title or _('AI Website Draft')), escape(key), safe_body)
            etree.fromstring(arch.encode('utf-8'))
        return arch

    def _apply_studio_preset(self, preset):
        self._check_manager()
        presets = {
            'product': {
                'mode': 'new_page',
                'edit_scope': 'full_page',
                'apply_strategy': 'new_unpublished',
                'page_blueprint': 'product',
                'design_style': 'premium_industrial',
                'content_depth': 'detailed',
                'conversion_action': 'quote',
                'page_goal': 'Explain the product range, build buyer trust, and collect quote enquiries.',
                'instruction': 'Create a premium product/category page with hero, applications, specifications, proof, buying process, catalogue CTA, and quote CTA.',
            },
            'landing': {
                'mode': 'new_page',
                'edit_scope': 'conversion',
                'apply_strategy': 'new_unpublished',
                'page_blueprint': 'landing',
                'design_style': 'conversion',
                'content_depth': 'balanced',
                'conversion_action': 'form',
                'page_goal': 'Convert campaign visitors into qualified enquiries.',
                'instruction': 'Create a high-converting landing page with offer hero, proof, objections, FAQs, and a clear lead action.',
            },
            'redesign': {
                'mode': 'improve_page',
                'edit_scope': 'layout',
                'apply_strategy': 'improved_copy',
                'page_blueprint': 'auto',
                'design_style': 'enterprise',
                'content_depth': 'balanced',
                'conversion_action': 'contact',
                'page_goal': 'Improve clarity, trust, visual hierarchy, and conversion without touching the live page.',
                'instruction': 'Redesign this page into a cleaner, more professional Website editor-friendly page with stronger first fold, better section order, clearer CTAs, and mobile-safe layout.',
            },
            'mobile': {
                'mode': 'mobile',
                'edit_scope': 'mobile',
                'apply_strategy': 'improved_copy',
                'page_blueprint': 'auto',
                'design_style': 'clean_b2b',
                'device_focus': 'mobile',
                'content_depth': 'compact',
                'conversion_action': 'whatsapp',
                'page_goal': 'Make the page easier to use on mobile and improve enquiry actions.',
                'instruction': 'Improve this page for mobile users with shorter headings, stacked sections, touch-friendly CTAs, no overflow, and a clear WhatsApp/contact action path.',
            },
            'crm_whatsapp': {
                'mode': 'crm_whatsapp',
                'edit_scope': 'conversion',
                'apply_strategy': 'new_unpublished',
                'page_blueprint': 'quote',
                'design_style': 'conversion',
                'content_depth': 'detailed',
                'conversion_action': 'whatsapp',
                'page_goal': 'Turn visitors into qualified CRM and WhatsApp enquiries without editing live CRM or WhatsApp records.',
                'instruction': 'Create a CRM and WhatsApp-ready landing page with buyer qualification, catalogue CTA, quote request path, WhatsApp enquiry CTA, support handoff, proof, FAQ, and clear next steps.',
            },
        }
        values = presets[preset]
        for draft in self:
            if draft.state == 'published':
                raise UserError(_("Published AI drafts cannot be changed. Create a new draft."))
            safe_values = dict(values)
            if draft.instruction and draft.instruction != _('AI Website Draft'):
                safe_values.pop('instruction', None)
            if draft.page_goal:
                safe_values.pop('page_goal', None)
            draft.write(safe_values)
        return True

    def action_preset_product_page(self):
        return self._apply_studio_preset('product')

    def action_preset_landing_page(self):
        return self._apply_studio_preset('landing')

    def action_preset_redesign(self):
        return self._apply_studio_preset('redesign')

    def action_preset_mobile(self):
        return self._apply_studio_preset('mobile')

    def action_preset_crm_whatsapp(self):
        return self._apply_studio_preset('crm_whatsapp')

    def _repair_ai_payload(self, original_output, quality_checklist, asset_candidates=False):
        self.ensure_one()
        repair_instruction = _(
            "%(base_prompt)s\n\n"
            "The previous AI response did not meet the production quality gate.\n"
            "Quality checklist:\n%(quality_checklist)s\n\n"
            "Previous response:\n%(original_output)s\n\n"
            "Repair requirements:\n"
            "- Return ONLY the required JSON object.\n"
            "- Build 6-9 Odoo Website editable sections for full-page work.\n"
            "- Include real business-specific content, not placeholders.\n"
            "- Include at least two CTA links using <a class='btn'>.\n"
            "- Include image_intents and image-ready markup or a clear visual section.\n"
            "- Keep output safe: no scripts, iframes, forms, inputs, QWeb, or external JS."
        ) % {
            'base_prompt': self._build_prompt_text(),
            'quality_checklist': quality_checklist or '',
            'original_output': (original_output or '')[:12000],
        }
        job = self.env['elsx.ai.job'].create_job(
            'custom',
            _('Website draft repair: %s') % self.name,
            origin=self,
            input_text=repair_instruction,
            input_payload={
                'repair': True,
                'draft_first': True,
                'asset_candidates': asset_candidates or self._asset_candidates_data(),
                'no_live_write': True,
            },
            prompt_code='website_builder_default',
        )
        job.action_run()
        output = job.response_text or job.response_json or ''
        return job, output, self._parse_ai_output(output)

    def action_generate_draft(self):
        for draft in self:
            draft._check_manager()
            if not draft.instruction:
                raise UserError(_("Please enter an instruction before generating a website draft."))
            original_arch = draft.source_page_id.arch if draft.source_page_id else ''
            job = self.env['elsx.ai.job'].create_job(
                'custom',
                _('Website draft: %s') % draft.name,
                origin=draft,
                input_text=draft._build_prompt_text(),
                input_payload={
                    'mode': draft.mode,
                    'edit_scope': draft.edit_scope,
                    'apply_strategy': draft.apply_strategy,
                    'section_position': draft.section_position,
                    'design_style': draft.design_style,
                    'page_blueprint': draft.page_blueprint,
                    'device_focus': draft.device_focus,
                    'content_depth': draft.content_depth,
                    'conversion_action': draft.conversion_action,
                    'business_context': draft.business_context or '',
                    'asset_guidance': draft.asset_guidance or '',
                    'target_audience': draft.target_audience or '',
                    'page_goal': draft.page_goal or '',
                    'brand_tone': draft.brand_tone,
                    'website_id': draft.website_id.id,
                    'source_page_id': draft.source_page_id.id,
                    'requested_url': draft.requested_url or '',
                    'revision_notes': draft.revision_notes or '',
                    'draft_first': True,
                    'publish_automatically': False,
                },
                prompt_code='website_builder_default',
            )
            try:
                job.action_run()
                output = job.response_text or job.response_json or ''
                payload = draft._parse_ai_output(output)
                asset_candidates = draft._asset_candidates_data()
                asset_candidate_text = draft._asset_candidate_text()
                asset_intents = draft._asset_intent_text(payload)
                raw_html = payload.get('html') or ''
                raw_css = payload.get('css') or ''
                if not draft._html_has_real_content(raw_html):
                    payload = draft._build_local_payload(_('AI did not provide usable website sections.'))
                    asset_intents = draft._asset_intent_text(payload)
                    raw_html = payload.get('html') or ''
                    raw_css = payload.get('css') or ''
                raw_html = draft._inject_asset_showcase(raw_html, asset_candidates)
                html = draft._sanitize_html(raw_html)
                css = draft._sanitize_css(raw_css)
                if not draft._html_has_real_content(html):
                    payload = draft._build_local_payload(_('AI output became empty after safety cleanup.'))
                    asset_intents = draft._asset_intent_text(payload)
                    raw_html = payload.get('html') or ''
                    raw_css = payload.get('css') or ''
                    raw_html = draft._inject_asset_showcase(raw_html, asset_candidates)
                    html = draft._sanitize_html(raw_html)
                    css = draft._sanitize_css(raw_css)
                section_plan = payload.get('section_plan') or draft._build_section_plan_text()
                seo_title = (payload.get('seo_title') or draft.name or '')[:255]
                seo_description = payload.get('seo_description') or False
                quality_score, quality_checklist = draft._quality_report(html, css, seo_title, seo_description)
                full_page_scope = draft.mode in ('new_page', 'improve_page', 'crm_whatsapp') and draft.edit_scope in (
                    'full_page', 'layout', 'conversion', 'seo', 'mobile', 'brand_system'
                )
                repair_note = False
                provider_type = job.provider_id.provider_type if job.provider_id else 'rules'
                if full_page_scope and quality_score < 74 and provider_type != 'rules':
                    try:
                        repair_job, repair_output, repair_payload = draft._repair_ai_payload(output, quality_checklist, asset_candidates)
                        repair_raw_html = draft._inject_asset_showcase(repair_payload.get('html') or '', asset_candidates)
                        repair_raw_css = repair_payload.get('css') or ''
                        repair_html = draft._sanitize_html(repair_raw_html)
                        repair_css = draft._sanitize_css(repair_raw_css)
                        repair_title = (repair_payload.get('seo_title') or draft.name or '')[:255]
                        repair_description = repair_payload.get('seo_description') or False
                        repair_score, repair_checklist = draft._quality_report(repair_html, repair_css, repair_title, repair_description)
                        if repair_score > quality_score:
                            job = repair_job
                            output = repair_output
                            payload = repair_payload
                            raw_html = repair_raw_html
                            raw_css = repair_raw_css
                            html = repair_html
                            css = repair_css
                            section_plan = repair_payload.get('section_plan') or draft._build_section_plan_text()
                            seo_title = repair_title
                            seo_description = repair_description
                            quality_score = repair_score
                            quality_checklist = repair_checklist
                            asset_intents = draft._asset_intent_text(repair_payload)
                            repair_note = _('Initial AI result was repaired once because it did not meet the page quality gate.')
                    except Exception as repair_exc:
                        repair_note = _('AI repair attempt failed, so the safe local page architecture was used: %s') % repair_exc

                if full_page_scope and quality_score < 74:
                    payload = draft._build_local_payload(
                        _('AI draft did not pass the production page quality gate, so ELSx generated a stronger editable page architecture.')
                    )
                    asset_intents = draft._asset_intent_text(payload)
                    raw_html = payload.get('html') or ''
                    raw_css = payload.get('css') or ''
                    raw_html = draft._inject_asset_showcase(raw_html, asset_candidates)
                    html = draft._sanitize_html(raw_html)
                    css = draft._sanitize_css(raw_css)
                    section_plan = payload.get('section_plan') or draft._build_section_plan_text()
                    seo_title = (payload.get('seo_title') or draft.name or '')[:255]
                    seo_description = payload.get('seo_description') or False
                    quality_score, quality_checklist = draft._quality_report(html, css, seo_title, seo_description)
                ai_warnings = draft._as_warning_text(payload.get('warnings'))
                if repair_note:
                    ai_warnings = '\n'.join(chunk for chunk in [ai_warnings, repair_note] if chunk)
                warnings = draft._merge_warnings(ai_warnings, draft._detect_safety_warnings(raw_html, raw_css))
                draft.write({
                    'state': 'generated',
                    'provider_id': job.provider_id.id,
                    'ai_job_id': job.id,
                    'original_arch': original_arch,
                    'raw_ai_output': output,
                    'ai_summary': payload.get('summary') or _('AI draft generated.'),
                    'section_plan': section_plan,
                    'quality_score': quality_score,
                    'quality_checklist': quality_checklist,
                    'draft_html': html,
                    'draft_css': css,
                    'asset_intents': asset_intents,
                    'asset_candidates': asset_candidate_text,
                    'seo_title': seo_title,
                    'seo_description': seo_description,
                    'seo_keywords': (payload.get('seo_keywords') or '')[:255],
                    'warnings': warnings,
                })
            except Exception as exc:
                draft.write({
                    'state': 'failed',
                    'ai_job_id': job.id,
                    'provider_id': job.provider_id.id,
                    'warnings': str(exc),
                })
                raise
        return True

    def action_create_unpublished_page(self):
        self.ensure_one()
        self._check_manager()
        if not self.draft_html:
            raise UserError(_("Generate an AI draft before creating an unpublished website page."))
        if self.target_page_id:
            raise UserError(_("This draft already has a website page. Open the preview or reset the draft before creating another copy."))
        website = self.website_id or self._default_website_id()
        title = self.seo_title or self.name
        slug = self._safe_slug(title)
        website_ctx = website.with_context(website_id=website.id)
        requested = (self.requested_url or '').strip()
        if requested and not requested.startswith('/'):
            requested = '/%s' % requested
        if not requested:
            requested = '/ai-drafts/%s' % slug
        url = website_ctx.get_unique_path(requested)
        key = website_ctx.get_unique_key('ai_draft_%s' % slug, template_module='elsx_ai_website_builder')
        arch = self._build_page_arch(title, self.draft_html, self.draft_css or '', key)
        page = self._website_page_model_for_create(website).create({
            'name': title,
            'type': 'qweb',
            'mode': 'primary',
            'url': url,
            'key': key,
            'website_id': website.id,
            'website_indexed': False,
            'is_published': False,
            'arch': arch,
            'website_meta_title': self.seo_title or False,
            'website_meta_description': self.seo_description or False,
            'website_meta_keywords': self.seo_keywords or False,
        })
        self.env['elsx.website.ai.version'].create({
            'draft_id': self.id,
            'page_id': page.id,
            'view_id': page.view_id.id,
            'original_arch': self.original_arch or '',
            'new_arch': arch,
            'note': _('Unpublished AI draft page created.'),
        })
        self.write({'state': 'page_created', 'target_page_id': page.id})
        return self.action_open_preview()

    def action_update_unpublished_page(self):
        self.ensure_one()
        self._check_manager()
        if not self.target_page_id:
            raise UserError(_("Create an unpublished page before updating it."))
        if self.target_page_id.is_published:
            raise UserError(_("This generated page is published. Unpublish or create a new copy before replacing its content."))
        if not self.draft_html:
            raise UserError(_("Generate a draft before updating the page copy."))
        title = self.seo_title or self.name
        arch = self._build_page_arch(title, self.draft_html, self.draft_css or '', self.target_page_id.key)
        self.env['elsx.website.ai.version'].create({
            'draft_id': self.id,
            'page_id': self.target_page_id.id,
            'view_id': self.target_page_id.view_id.id,
            'original_arch': self.target_page_id.arch or '',
            'new_arch': arch,
            'note': _('Unpublished AI page copy updated from latest draft.'),
        })
        self.target_page_id.write({
            'arch': arch,
            'website_meta_title': self.seo_title or False,
            'website_meta_description': self.seo_description or False,
            'website_meta_keywords': self.seo_keywords or False,
        })
        self.state = 'page_created'
        return self.action_open_preview()

    def action_clone_source_page(self):
        self.ensure_one()
        self._check_manager()
        if not self.source_page_id:
            raise UserError(_("Select a source page before cloning it."))
        if self.target_page_id:
            raise UserError(_("This draft already has a generated page. Create a new AI draft to clone again."))
        website = self.website_id or self.source_page_id.website_id or self._default_website_id()
        title = _('%s - AI Working Copy') % self.source_page_id.name
        slug = self._safe_slug(title)
        website_ctx = website.with_context(website_id=website.id)
        url = website_ctx.get_unique_path('/ai-copies/%s' % slug)
        key = website_ctx.get_unique_key('ai_copy_%s' % slug, template_module='elsx_ai_website_builder')
        source_arch = self.source_page_id.arch or ''
        arch = source_arch.replace('t-name="%s"' % self.source_page_id.key, 't-name="%s"' % key, 1)
        if arch == source_arch:
            arch = self._build_page_arch(title, source_arch, '', key)
        page = self._website_page_model_for_create(website).create({
            'name': title,
            'type': 'qweb',
            'mode': 'primary',
            'url': url,
            'key': key,
            'website_id': website.id,
            'website_indexed': False,
            'is_published': False,
            'arch': arch,
            'website_meta_title': self.source_page_id.website_meta_title or title,
            'website_meta_description': self.source_page_id.website_meta_description or False,
            'website_meta_keywords': self.source_page_id.website_meta_keywords or False,
        })
        self.env['elsx.website.ai.version'].create({
            'draft_id': self.id,
            'page_id': page.id,
            'view_id': page.view_id.id,
            'original_arch': source_arch,
            'new_arch': arch,
            'note': _('Unpublished working copy cloned from source page.'),
        })
        self.write({
            'state': 'page_created',
            'target_page_id': page.id,
            'original_arch': source_arch,
            'ai_summary': self.ai_summary or _('Source page cloned as an unpublished working copy.'),
        })
        return self.action_open_preview()

    def action_open_preview(self):
        self.ensure_one()
        if not self.target_page_id:
            raise UserError(_("Create an unpublished page before opening a preview."))
        return {
            'type': 'ir.actions.act_url',
            'url': self.target_page_id.url,
            'target': 'new',
        }

    def action_open_editor(self):
        self.ensure_one()
        self._check_manager()
        if not self.target_page_id:
            raise UserError(_("Create an unpublished page before opening the editor."))
        separator = '&' if '?' in self.target_page_id.url else '?'
        return {
            'type': 'ir.actions.act_url',
            'url': '%s%senable_editor=1' % (self.target_page_id.url, separator),
            'target': 'new',
        }

    def action_publish_page(self):
        for draft in self:
            draft._check_manager()
            if not draft.target_page_id:
                raise UserError(_("Create an unpublished page before publishing."))
            if draft.target_page_id.is_published:
                draft.write({
                    'state': 'published',
                    'published_by_id': draft.published_by_id.id or self.env.user.id,
                    'published_date': draft.published_date or fields.Datetime.now(),
                })
                continue
            draft.env['elsx.website.ai.version'].create({
                'draft_id': draft.id,
                'page_id': draft.target_page_id.id,
                'view_id': draft.target_page_id.view_id.id,
                'original_arch': draft.original_arch or '',
                'new_arch': draft.target_page_id.arch or '',
                'note': _('AI draft page published manually by %s.') % self.env.user.display_name,
            })
            draft.target_page_id.write({
                'is_published': True,
                'date_publish': False,
            })
            draft.write({
                'state': 'published',
                'published_by_id': self.env.user.id,
                'published_date': fields.Datetime.now(),
            })
        return True

    def action_unpublish_page(self):
        for draft in self:
            draft._check_manager()
            if not draft.target_page_id:
                raise UserError(_("No generated page is linked to this draft."))
            draft.env['elsx.website.ai.version'].create({
                'draft_id': draft.id,
                'page_id': draft.target_page_id.id,
                'view_id': draft.target_page_id.view_id.id,
                'original_arch': draft.original_arch or '',
                'new_arch': draft.target_page_id.arch or '',
                'note': _('AI draft page unpublished manually by %s.') % self.env.user.display_name,
            })
            draft.target_page_id.is_published = False
            draft.write({
                'state': 'page_created',
                'published_by_id': False,
                'published_date': False,
            })
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        self._check_manager()
        if any(draft.target_page_id and draft.target_page_id.is_published for draft in self):
            raise UserError(_("Unpublish the generated page before resetting this draft."))
        self.write({'state': 'draft'})
        return True


class ElsxCeAiCommand(models.Model):
    _name = 'elsx.ce.ai.command'
    _description = 'ELSx CE AI Command Center'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('AI Command'))
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('generated', 'Generated'),
        ('handed_off', 'Handed Off'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, index=True)
    command_type = fields.Selection([
        ('website_page', 'Website Page / Builder'),
        ('website_redesign', 'Website Redesign'),
        ('website_section', 'Website Section'),
        ('seo', 'SEO / Content Strategy'),
        ('crm', 'CRM Playbook'),
        ('whatsapp', 'WhatsApp Marketing'),
        ('campaign', 'Campaign Plan'),
        ('module_spec', 'Odoo Module Spec'),
        ('workflow', 'Business Workflow'),
        ('ux_review', 'UI / UX Review'),
        ('data_plan', 'Data Cleanup Plan'),
        ('custom', 'Custom AI Work'),
    ], default='website_page', required=True)
    execution_mode = fields.Selection([
        ('analysis', 'Analysis Only'),
        ('draft', 'Draft Artifact'),
        ('website_draft', 'Create Website Builder Draft'),
    ], default='draft', required=True)
    risk_level = fields.Selection([
        ('safe', 'Safe Draft'),
        ('review', 'Needs Manager Review'),
        ('sensitive', 'Sensitive / Production Review'),
    ], default='safe', readonly=True)
    instruction = fields.Text(required=True)
    business_context = fields.Text()
    constraints = fields.Text(
        default=lambda self: _(
            "Do not modify live records. Do not ask for secrets. Do not generate scripts, unsafe forms, "
            "license bypasses, credential capture, or direct database changes. Produce draft-first work."
        )
    )
    target_model = fields.Char(
        help='Optional technical model name for context only, for example website.page, crm.lead, whatsapp.campaign.'
    )
    target_record_id = fields.Integer(help='Optional record id for context only. The command center does not edit it.')
    website_id = fields.Many2one('website', ondelete='set null')
    source_page_id = fields.Many2one('website.page', ondelete='set null')
    provider_id = fields.Many2one('elsx.ai.provider', readonly=True, ondelete='set null')
    ai_job_id = fields.Many2one('elsx.ai.job', readonly=True, ondelete='set null')
    website_draft_id = fields.Many2one('elsx.website.ai.draft', readonly=True, ondelete='set null')
    result_summary = fields.Text(readonly=True)
    result_markdown = fields.Text(readonly=True)
    result_json = fields.Text(readonly=True)
    recommended_actions = fields.Text(readonly=True)
    safety_notes = fields.Text(readonly=True)
    quality_score = fields.Integer(readonly=True)
    result_preview_html = fields.Html(compute='_compute_result_preview_html', sanitize=False)

    def _check_manager(self):
        if not self.env.user.has_group('elsx_ai_website_builder.group_ai_website_builder_manager'):
            raise AccessError(_("Only ELSx AI Studio managers can use the ELSx CE AI Command Center."))

    @api.depends('result_summary', 'result_markdown', 'recommended_actions', 'safety_notes')
    def _compute_result_preview_html(self):
        for command in self:
            if not any([command.result_summary, command.result_markdown, command.recommended_actions, command.safety_notes]):
                command.result_preview_html = False
                continue
            chunks = []
            for title, value in [
                (_('Summary'), command.result_summary),
                (_('Draft Artifact'), command.result_markdown),
                (_('Recommended Actions'), command.recommended_actions),
                (_('Safety Notes'), command.safety_notes),
            ]:
                if value:
                    chunks.append('<section class="mb-4"><h3>%s</h3>%s</section>' % (
                        escape(title),
                        plaintext2html(value, container_tag='div'),
                    ))
            command.result_preview_html = Markup('<div class="o_elsx_ai_preview_shell">%s</div>') % Markup(''.join(chunks))

    def _plain_text(self, value):
        text = HTML_TAG_RE.sub(' ', value or '')
        return re.sub(r'\s+', ' ', text).strip()

    def _json_loads_relaxed(self, text):
        cleaned = (text or '').strip()
        if not cleaned:
            return {}
        json_match = JSON_FENCE_RE.search(cleaned)
        if json_match:
            cleaned = json_match.group(1).strip()
        cleaned = FENCE_RE.sub('', cleaned).strip()
        try:
            payload = json.loads(cleaned)
        except Exception:
            first = cleaned.find('{')
            last = cleaned.rfind('}')
            if first >= 0 and last > first:
                try:
                    payload = json.loads(cleaned[first:last + 1])
                except Exception:
                    payload = {}
            else:
                payload = {}
        return payload if isinstance(payload, dict) else {}

    def _command_guides(self):
        return {
            'website_page': 'Produce a full Website Builder-ready page plan and copy, suitable for handoff to ELSx AI Studio.',
            'website_redesign': 'Review an existing page and propose a safer stronger unpublished redesign path.',
            'website_section': 'Produce one reusable Website section with purpose, copy, CTA, and layout instructions.',
            'seo': 'Create SEO title, description, topic map, headings, internal CTA plan, and content gaps.',
            'crm': 'Create a CRM operating playbook: stages, fields, lead qualification, activities, and WhatsApp handoff.',
            'whatsapp': 'Create WhatsApp-safe campaign/template/flow recommendations using approved-template discipline.',
            'campaign': 'Create a campaign plan with audience, offer, A/B copy, compliance checks, and reply handling.',
            'module_spec': 'Create a technical Odoo module spec with models, views, security, deployment, tests, and rollback notes.',
            'workflow': 'Create a practical business workflow with roles, screens, automations, and audit trail.',
            'ux_review': 'Review UI/UX and produce prioritized improvements with no destructive changes.',
            'data_plan': 'Create a cleanup/migration plan with backup-first rules and no direct SQL execution.',
            'custom': 'Produce a structured, safe, draft-first business/technical artifact.',
        }

    def _build_command_prompt(self):
        self.ensure_one()
        guide = self._command_guides().get(self.command_type, '')
        source = ''
        if self.source_page_id:
            source = (self.source_page_id.arch or '')[:10000]
        return _(
            "You are ELSxGlobal's Odoo Community Edition AI Command Center.\n"
            "Goal: unlock advanced AI workflows in Odoo CE using safe custom modules, not Enterprise license bypasses.\n"
            "Command type: %(command_type)s\n"
            "Guide: %(guide)s\n"
            "Execution mode: %(execution_mode)s\n"
            "Instruction: %(instruction)s\n"
            "Business context: %(business_context)s\n"
            "Constraints: %(constraints)s\n"
            "Target model: %(target_model)s\n"
            "Target record id: %(target_record_id)s\n"
            "Return ONLY JSON with keys: summary, artifact_markdown, recommended_actions, safety_notes, risk_level, quality_score.\n"
            "quality_score must be 0-100. risk_level must be safe, review, or sensitive.\n"
            "Be specific, operational, and implementation-ready. Avoid generic marketing filler.\n"
            "Never suggest editing live production data without backup and manual approval. Never suggest bypassing licenses or security.\n"
            "If this is website work, include a strong page/section architecture that can be handed to ELSx AI Studio.\n"
            "Source page XML/context, if any:\n%(source)s"
        ) % {
            'command_type': dict(self._fields['command_type'].selection).get(self.command_type, self.command_type),
            'guide': guide,
            'execution_mode': dict(self._fields['execution_mode'].selection).get(self.execution_mode, self.execution_mode),
            'instruction': self.instruction or '',
            'business_context': self.business_context or '',
            'constraints': self.constraints or '',
            'target_model': self.target_model or '',
            'target_record_id': self.target_record_id or '',
            'source': source,
        }

    def _fallback_payload(self, reason=False):
        self.ensure_one()
        guide = self._command_guides().get(self.command_type, '')
        artifact = _(
            "## Objective\n%(instruction)s\n\n"
            "## Operating Mode\nDraft-first ELSx CE AI workflow. No live data is changed automatically.\n\n"
            "## Architecture\n- Use existing Odoo CE models and custom addon inheritance.\n"
            "- Keep production records untouched until an authorized user applies a reviewed change.\n"
            "- Reuse configured ELSx AI providers; never store secrets in Git.\n"
            "- Create previews, snapshots, and rollback notes before any user-approved apply step.\n\n"
            "## Implementation Direction\n%(guide)s\n\n"
            "## Production Guardrails\n- Backup before upgrades.\n"
            "- Module changes through safe deployment scripts.\n"
            "- Manager-only apply permissions.\n"
            "- Logs reviewed after deployment.\n"
            "- No direct SQL, no credential capture, no license bypass, no webhook or payment changes unless explicitly scoped.\n"
        ) % {
            'instruction': self.instruction or _('AI command'),
            'guide': guide or _('Create a structured safe implementation plan.'),
        }
        return {
            'summary': reason or _('Safe CE AI draft artifact generated from the command.'),
            'artifact_markdown': artifact,
            'recommended_actions': _(
                "1. Review the draft artifact.\n"
                "2. If it is website work, create a Website Builder draft.\n"
                "3. Test on a staging/copy database.\n"
                "4. Deploy with backup-first safe update only after approval."
            ),
            'safety_notes': _(
                "This command center produces drafts only. It does not edit live records, install modules, uninstall modules, "
                "run SQL, publish pages, or change credentials."
            ),
            'risk_level': 'safe',
            'quality_score': 82,
        }

    def _parse_ai_payload(self, output):
        payload = self._json_loads_relaxed(output)
        if payload:
            return payload
        text = self._plain_text(output)
        if text:
            payload = self._fallback_payload(_('AI returned unstructured text, so it was converted into a safe draft artifact.'))
            payload['artifact_markdown'] = output
            payload['quality_score'] = max(65, min(90, len(text) // 40))
            return payload
        return self._fallback_payload(_('AI returned an empty response.'))

    def _quality_from_payload(self, payload):
        try:
            score = int(payload.get('quality_score') or 0)
        except Exception:
            score = 0
        artifact_text = self._plain_text(payload.get('artifact_markdown') or '')
        if not score:
            score = 50
            if len(artifact_text) > 1000:
                score += 20
            if '##' in (payload.get('artifact_markdown') or ''):
                score += 10
            if payload.get('recommended_actions'):
                score += 10
            if payload.get('safety_notes'):
                score += 10
        return max(0, min(100, score))

    def action_run_command(self):
        for command in self:
            command._check_manager()
            if not command.instruction:
                raise UserError(_("Enter a command before running AI."))
            command.state = 'running'
            job = self.env['elsx.ai.job'].create_job(
                'custom',
                _('CE AI command: %s') % command.name,
                origin=command,
                input_text=command._build_command_prompt(),
                input_payload={
                    'command_type': command.command_type,
                    'execution_mode': command.execution_mode,
                    'target_model': command.target_model or '',
                    'target_record_id': command.target_record_id or False,
                    'draft_first': True,
                    'no_live_write': True,
                    'no_license_bypass': True,
                },
                prompt_code='ce_ai_command_center',
            )
            try:
                job.action_run()
                output = job.response_text or job.response_json or ''
                payload = command._parse_ai_payload(output)
                quality = command._quality_from_payload(payload)
                risk = payload.get('risk_level') if payload.get('risk_level') in ('safe', 'review', 'sensitive') else 'review'
                command.write({
                    'state': 'generated',
                    'provider_id': job.provider_id.id,
                    'ai_job_id': job.id,
                    'result_summary': payload.get('summary') or _('AI command generated.'),
                    'result_markdown': payload.get('artifact_markdown') or '',
                    'result_json': json.dumps(payload, ensure_ascii=False, indent=2),
                    'recommended_actions': payload.get('recommended_actions') or '',
                    'safety_notes': payload.get('safety_notes') or '',
                    'quality_score': quality,
                    'risk_level': risk,
                })
            except Exception as exc:
                command.write({
                    'state': 'failed',
                    'provider_id': job.provider_id.id,
                    'ai_job_id': job.id,
                    'safety_notes': str(exc),
                    'risk_level': 'review',
                })
                raise
        return True

    def action_create_website_builder_draft(self):
        self.ensure_one()
        self._check_manager()
        if self.command_type not in ('website_page', 'website_redesign', 'website_section', 'seo', 'ux_review'):
            raise UserError(_("Website Builder handoff is available only for website, SEO, and UX commands."))
        if not self.result_markdown and self.state != 'generated':
            raise UserError(_("Run the AI command before creating a Website Builder draft."))
        mode = 'new_page'
        edit_scope = 'full_page'
        apply_strategy = 'new_unpublished'
        if self.command_type == 'website_redesign':
            mode = 'improve_page'
            apply_strategy = 'improved_copy'
        elif self.command_type == 'website_section':
            mode = 'add_section'
            edit_scope = 'section'
            apply_strategy = 'section_draft'
        elif self.command_type == 'seo':
            mode = 'seo'
            edit_scope = 'seo'
        elif self.command_type == 'ux_review':
            mode = 'improve_page'
            edit_scope = 'layout'
            apply_strategy = 'improved_copy'
        draft = self.env['elsx.website.ai.draft'].create({
            'name': _('Website draft from: %s') % self.name,
            'mode': mode,
            'edit_scope': edit_scope,
            'apply_strategy': apply_strategy,
            'design_style': 'enterprise',
            'page_blueprint': 'auto',
            'device_focus': 'all',
            'content_depth': 'detailed',
            'conversion_action': 'quote',
            'website_id': self.website_id.id or False,
            'source_page_id': self.source_page_id.id or False,
            'instruction': '\n\n'.join(filter(None, [self.instruction, self.result_markdown])),
            'business_context': self.business_context or self.result_summary or '',
            'asset_guidance': self.recommended_actions or '',
            'page_goal': self.result_summary or self.name,
        })
        self.write({'state': 'handed_off', 'website_draft_id': draft.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('ELSx AI Studio'),
            'res_model': 'elsx.website.ai.draft',
            'res_id': draft.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_website_draft(self):
        self.ensure_one()
        if not self.website_draft_id:
            raise UserError(_("No Website Builder draft is linked yet."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('ELSx AI Studio'),
            'res_model': 'elsx.website.ai.draft',
            'res_id': self.website_draft_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_to_draft(self):
        self._check_manager()
        self.write({'state': 'draft'})
        return True

    def action_cancel(self):
        self._check_manager()
        self.write({'state': 'cancelled'})
        return True


class ElsxWebsiteAiVersion(models.Model):
    _name = 'elsx.website.ai.version'
    _description = 'ELSx AI Website Version Snapshot'
    _order = 'create_date desc, id desc'

    draft_id = fields.Many2one('elsx.website.ai.draft', required=True, ondelete='cascade')
    page_id = fields.Many2one('website.page', ondelete='set null')
    view_id = fields.Many2one('ir.ui.view', ondelete='set null')
    original_arch = fields.Text(readonly=True)
    new_arch = fields.Text(readonly=True)
    applied_by_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    applied_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    note = fields.Char(readonly=True)


class WebsitePage(models.Model):
    _inherit = 'website.page'

    def action_open_ai_builder(self):
        self.ensure_one()
        if not self.env.user.has_group('elsx_ai_website_builder.group_ai_website_builder_manager'):
            raise AccessError(_("Only ELSx AI Studio managers can improve website pages with AI."))
        draft = self.env['elsx.website.ai.draft'].create({
            'name': _('AI improvement: %s') % self.name,
            'mode': 'improve_page',
            'edit_scope': 'full_page',
            'apply_strategy': 'improved_copy',
            'design_style': 'enterprise',
            'page_blueprint': 'auto',
            'device_focus': 'all',
            'content_depth': 'balanced',
            'conversion_action': 'quote',
            'source_page_id': self.id,
            'website_id': self.website_id.id or self.env['website'].get_current_website().id,
            'instruction': _('Improve this developed page like a professional website studio: stronger first fold, clearer sections, better copy hierarchy, stronger CTA, SEO polish, and mobile-safe layout. Keep the result safe and unpublished.'),
            'page_goal': _('Improve conversion and clarity without changing the live page.'),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('ELSx AI Studio'),
            'res_model': 'elsx.website.ai.draft',
            'res_id': draft.id,
            'view_mode': 'form',
            'target': 'current',
        }
