"""Preserve demonstrable agent membership before removing blanket access."""
import json


def migrate(cr, version):
    cr.execute("SELECT id FROM res_company ORDER BY id")
    companies = [row[0] for row in cr.fetchall()]
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='whatsapp_account'")
    if 'company_id' not in {row[0] for row in cr.fetchall()}:
        cr.execute('ALTER TABLE whatsapp_account ADD COLUMN company_id integer REFERENCES res_company(id)')
    cr.execute("SELECT value FROM ir_config_parameter WHERE key='whatsapp.account.company_mapping'")
    configured = cr.fetchone()
    mapping = json.loads(configured[0]) if configured else {}
    cr.execute('SELECT id FROM whatsapp_account WHERE company_id IS NULL')
    for (account_id,) in cr.fetchall():
        company = mapping.get(str(account_id)) or (companies[0] if len(companies) == 1 else None)
        if company not in companies:
            raise RuntimeError('Configure whatsapp.account.company_mapping before this multi-company upgrade.')
        cr.execute('UPDATE whatsapp_account SET company_id=%s WHERE id=%s', [company, account_id])
    cr.execute('''SELECT a.id FROM whatsapp_account a
                  WHERE EXISTS (SELECT 1 FROM whatsapp_chat c WHERE c.account_id=a.id)
                  AND NOT EXISTS (SELECT 1 FROM whatsapp_team_member t WHERE t.account_id=a.id)
                  AND NOT EXISTS (SELECT 1 FROM whatsapp_chat c WHERE c.account_id=a.id AND c.assigned_user_id IS NOT NULL)''')
    if cr.fetchall():
        raise RuntimeError('Existing inboxes without an identifiable team require access mapping before upgrade.')
    cr.execute('''INSERT INTO res_groups_users_rel (gid, uid)
                  SELECT d.res_id, agents.uid FROM ir_model_data d CROSS JOIN (
                    SELECT user_id AS uid FROM whatsapp_team_member
                    UNION SELECT assigned_user_id FROM whatsapp_chat WHERE assigned_user_id IS NOT NULL
                  ) agents
                  WHERE d.module='elsx_whatsapp_marketing' AND d.name='group_whatsapp_user'
                  ON CONFLICT DO NOTHING''')
