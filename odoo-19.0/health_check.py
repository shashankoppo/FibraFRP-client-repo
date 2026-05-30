import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

registry = Registry('qwerty')
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})

    print('=' * 70)
    print('COMPREHENSIVE SYSTEM HEALTH CHECK')
    print('=' * 70)

    # 1. Module state
    module = env['ir.module.module'].search([('name', '=', 'elsx_whatsapp_marketing')])
    print(f'\n1. Module state: {module.state}')

    # 2. Check needs_reply field exists
    try:
        fields = env['whatsapp.chat'].fields_get(['needs_reply'])
        has_field = 'needs_reply' in fields
        ftype = fields.get('needs_reply', {}).get('type', 'N/A')
        status = 'EXISTS' if has_field else 'MISSING'
        print(f'2. needs_reply field: {status} (type={ftype})')
    except Exception as e:
        print(f'2. needs_reply field: ERROR - {e}')

    # 3. Chat counts by state
    all_chats = env['whatsapp.chat'].search_count([])
    open_chats = env['whatsapp.chat'].search_count([('state', '=', 'open')])
    resolved_chats = env['whatsapp.chat'].search_count([('state', '=', 'resolved')])
    snoozed_chats = env['whatsapp.chat'].search_count([('state', '=', 'snoozed')])
    archived = env['whatsapp.chat'].search_count([('is_archived', '=', True)])
    not_archived = env['whatsapp.chat'].search_count([('is_archived', '=', False)])
    print(f'3. Chat stats: total={all_chats}, open={open_chats}, resolved={resolved_chats}, snoozed={snoozed_chats}, archived={archived}, active={not_archived}')

    # 4. Test get_sidebar_counts for each filter
    for filt in ['all', 'open', 'mine', 'unread', 'resolved', 'snoozed']:
        try:
            counts = env['whatsapp.chat'].get_sidebar_counts(filter_type=filt)
            print(f'4. Sidebar counts (filter={filt}): active={counts["active"]}, request={counts["request"]}, intervened={counts["intervened"]}')
        except Exception as e:
            print(f'4. Sidebar counts (filter={filt}): ERROR - {e}')

    # 5. Test get_sidebar_chats for each pane
    for pane in ['active', 'request', 'intervened']:
        try:
            chats = env['whatsapp.chat'].get_sidebar_chats(pane=pane, limit=5)
            print(f'5. Sidebar chats (pane={pane}): returned {len(chats)} chats')
        except Exception as e:
            print(f'5. Sidebar chats (pane={pane}): ERROR - {e}')

    # 6. Test resolved filter on get_sidebar_chats
    for pane in ['active', 'request', 'intervened']:
        try:
            chats = env['whatsapp.chat'].get_sidebar_chats(pane=pane, filter_type='resolved', limit=5)
            print(f'6. Resolved chats (pane={pane}): returned {len(chats)} chats')
        except Exception as e:
            print(f'6. Resolved chats (pane={pane}): ERROR - {e}')

    # 7. Check action_resolve method for is_archived
    try:
        import inspect
        resolve_src = inspect.getsource(env['whatsapp.chat'].__class__.action_resolve)
        has_is_archived = 'is_archived' in resolve_src
        if has_is_archived:
            print('7. action_resolve: STILL sets is_archived (needs fix)')
        else:
            print('7. action_resolve: FIXED (no is_archived)')
    except Exception as e:
        print(f'7. action_resolve check: ERROR - {e}')

    # 8. Dashboard action
    actions = env['ir.actions.client'].search([('tag', '=', 'whatsapp_marketing_dashboard')])
    for a in actions:
        print(f'8. Dashboard client action: id={a.id}, name={a.name}, tag={a.tag}')
    if not actions:
        print('8. Dashboard client action: NONE FOUND')

    # 9. CRM action methods exist
    has_opp = hasattr(env['whatsapp.chat'], 'action_create_opportunity')
    has_quote = hasattr(env['whatsapp.chat'], 'action_create_quote')
    print(f'9. CRM quick actions: create_opportunity={has_opp}, create_quote={has_quote}')

    # 10. Assignment log table
    try:
        assignments = env['whatsapp.conversation.assignment'].search_count([])
        print(f'10. Conversation assignment logs: {assignments} records')
    except Exception as e:
        print(f'10. Conversation assignment logs: ERROR - {e}')

    # 11. Check intervened pane domain (no user filter)
    try:
        import inspect
        sidebar_src = inspect.getsource(env['whatsapp.chat'].__class__.get_sidebar_chats)
        # Check that intervened pane does NOT filter by assigned_user_id
        if "pane == 'intervened'" in sidebar_src:
            # Find the block after this condition
            idx = sidebar_src.index("pane == 'intervened'")
            block = sidebar_src[idx:idx+300]
            if 'assigned_user_id' in block and '!=' in block:
                print('11. Intervened pane: STILL has user filter (needs fix)')
            else:
                print('11. Intervened pane: FIXED (no user-specific filter)')
        else:
            print('11. Intervened pane: could not find pane check in source')
    except Exception as e:
        print(f'11. Intervened pane check: ERROR - {e}')

    print()
    print('=' * 70)
    print('HEALTH CHECK COMPLETE')
    print('=' * 70)
