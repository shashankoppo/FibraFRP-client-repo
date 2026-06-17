# ELSx AI Studio

Draft-first AI website studio and ELSx CE AI Command Center. It reuses Odoo Website, Odoo media/product assets, and configured ELSx AI providers to generate editable unpublished pages.

## Safety Rules

- Uses existing `elsx.ai.provider` records, including NVIDIA NIM when configured.
- Does not store API keys in code.
- Does not edit live published pages automatically.
- Creates unpublished, non-indexed website pages for review.
- Publishes only when an authorized manager clicks **Publish Page**.
- Stores page snapshots before publish/unpublish actions.
- Strips unsafe AI output: scripts, iframes, forms, inline event handlers, QWeb directives, and JavaScript URLs.
- Uses Odoo media, product images, company assets, and configured Website media sources before any generic visual fallback.
- Retries weak AI output once and then falls back to a business-aware editable page architecture.
- Only users in **ELSx AI Studio Manager** can generate, create, edit, publish, or unpublish AI pages.
- The CE AI Command Center never bypasses Odoo Enterprise licensing or security. It builds safe custom-addon drafts, specs, playbooks, and website handoffs.

## Usage

1. Install `elsx_ai_website_builder`.
2. Give trusted website/SaaS admins the **ELSx AI Studio Manager** group.
3. Open **Website > Site > CE AI Command Center** for broad AI work, or **Website > Site > ELSx AI Studio** for page drafts.
4. Select a mode, edit scope, design style, device focus, CTA, and apply strategy.
5. Enter a command in normal language, plus business context and asset guidance.
6. Review preview, warnings, generated HTML/CSS, SEO, and diff.
7. Create an unpublished page copy, clone a source page, or update the unpublished AI copy.
8. Open the generated copy in the Website editor for manual design polish.
9. Publish manually only after review.

## Website Studio Workflow

- **Command-first**: write what you want, similar to a website builder prompt.
- **Source-aware**: select an existing website page to improve, clone, redesign, or create a safer copy.
- **Scope-aware**: target the full page, hero, section, copy, layout, conversion path, SEO, mobile, or brand system.
- **Style-aware**: choose enterprise, premium industrial, clean B2B, conversion landing, editorial, minimal, or bold modern.
- **Revision-friendly**: use **Revision / Follow-up Command** and click **Generate / Revise Draft** again.
- **Safe apply**: use **Update Unpublished Page** to replace only the generated working copy.
- **Manual final control**: use **Open Editor** for Odoo's visual editor, then publish only when approved.
- **Asset-aware**: choose whether the draft should prioritize Odoo media, product images, brand assets, or no images.

## Builder Modes

- **New Page**: full unpublished landing page draft.
- **Improve Current Page**: manager starts from an existing page and generates a safer improved copy.
- **Add Section**: creates one reusable section for review.
- **SEO Polish**: improves metadata, headings, and search-friendly copy.
- **Mobile Fix Suggestions**: creates concise responsive content/layout suggestions.
- **CTA / Form Section**: creates conversion-focused CTA content without raw credential-capture forms.
- **CRM / WhatsApp Landing Page**: creates a safe lead-generation page with quote, catalogue, WhatsApp enquiry, and CRM qualification sections.

## ELSx CE AI Command Center

Use this when the request is bigger than a single website page.

- **Website Page / Builder**: create a page architecture and hand it to ELSx AI Studio.
- **Website Redesign**: review an existing page and produce an unpublished redesign handoff.
- **Website Section**: generate a reusable page section plan.
- **SEO / Content Strategy**: build title, description, headings, content gaps, and CTA plan.
- **CRM Playbook**: draft CRM stages, lead qualification, activities, and WhatsApp handoff.
- **WhatsApp Marketing**: draft campaign/template/flow strategy while respecting approved-template behavior.
- **Campaign Plan**: draft audience, offer, A/B variants, compliance checks, and reply handling.
- **Odoo Module Spec**: draft models, views, security, tests, deployment, rollback, and data-safety notes.
- **Business Workflow**: draft role-based operating workflows.
- **UI / UX Review**: produce prioritized usability improvements.
- **Data Cleanup Plan**: produce backup-first cleanup plans without running SQL.

Command Center output can be handed to the Website Builder when it is website-related. It remains draft-only until a manager explicitly applies it through the correct Odoo workflow.

## Governance Notes

- Existing published pages are never modified in place by the AI.
- Improving a page creates a separate unpublished page copy.
- Updating a generated page replaces only the unpublished AI working copy.
- Cloning a source page creates a private unpublished working copy for design experiments.
- SEO title, description, and keywords are generated as metadata on the draft page.
- Unsafe AI output is stripped and reported in the warnings panel.
- System administrators inherit the manager group, but normal website users do not.

## Production Deployment

Use the existing safe deployment flow:

```bash
EXTRA_INSTALL_MODULES=elsx_ai_website_builder \
EXTRA_UPGRADE_MODULES=elsx_ai_website_builder \
bash deploy/safe_production_update.sh FiberaFRP_DB
```

Replace `FiberaFRP_DB` with the target database name.

## License Hygiene

This addon does not remove required Odoo or third-party license notices and does not bypass proprietary features. Use the read-only audit helper before cleanup:

```bash
bash deploy/audit_license_hygiene.sh
```

Only remove duplicate or accidental custom license clutter after reviewing the report. Keep upstream notices and manifest `license` keys.
