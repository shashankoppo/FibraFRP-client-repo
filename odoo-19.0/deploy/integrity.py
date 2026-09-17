"""Read-only fingerprints of business records, consent, and existing attachments."""
import hashlib
import json
from pathlib import Path

from psycopg2 import sql


TABLES = {
    'res_partner': ['id', 'name', 'phone', 'email', 'whatsapp_opt_in'],
    'sale_order': ['id', 'name', 'partner_id', 'state', 'amount_total'],
    'sale_order_line': ['id', 'order_id', 'product_id', 'product_uom_qty', 'price_unit'],
    'purchase_order': ['id', 'name', 'partner_id', 'state', 'amount_total'],
    'stock_move': ['id', 'product_id', 'state', 'product_uom_qty', 'location_id', 'location_dest_id'],
    'stock_quant': ['id', 'product_id', 'location_id', 'quantity', 'reserved_quantity'],
    'crm_lead': ['id', 'name', 'partner_id', 'stage_id', 'expected_revenue'],
    'account_move': ['id', 'name', 'partner_id', 'state', 'amount_total', 'amount_residual'],
    'account_move_line': ['id', 'move_id', 'account_id', 'debit', 'credit', 'balance', 'amount_currency'],
    'whatsapp_message': ['id', 'account_id', 'partner_id', 'body', 'status', 'message_id', 'next_retry_at'],
    'whatsapp_chat': ['id', 'account_id', 'partner_id', 'phone_number', 'assigned_user_id'],
    'whatsapp_contact': ['id', 'partner_id', 'phone_number', 'opt_in', 'opt_out_date'],
    'whatsapp_consent_log': ['id', 'partner_id', 'account_id', 'consent_type', 'status', 'consent_date', 'source', 'ip_address', 'user_agent'],
    'whatsapp_campaign': ['id', 'account_id', 'name', 'state'],
}


def snapshot(cr, data_dir, database, expected=None):
    result = {'tables': {}, 'files': {}}
    for table, fields in TABLES.items():
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s", [table])
        available = {row[0] for row in cr.fetchall()}
        if expected is not None:
            if table not in expected['tables']:
                continue
            columns = expected['tables'][table]['columns']
        else:
            columns = [name for name in fields if name in available]
        if not columns:
            continue
        digest, count = hashlib.sha256(), 0
        cr.execute(sql.SQL('SELECT {} FROM {} ORDER BY id').format(
            sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table)))
        while rows := cr.fetchmany(1000):
            for row in rows:
                digest.update(json.dumps(row, default=str, ensure_ascii=True, separators=(',', ':')).encode())
                digest.update(b'\n')
                count += 1
        result['tables'][table] = {'columns': columns, 'count': count, 'sha256': digest.hexdigest()}
    path = Path(data_dir) / 'filestore' / database
    if expected is None:
        cr.execute("SELECT DISTINCT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL")
        filenames = [row[0] for row in cr.fetchall()]
    else:
        filenames = expected['files']
    for name in filenames:
        file = (path / name).resolve()
        if not file.is_relative_to(path.resolve()) or not file.is_file():
            raise RuntimeError('An existing attachment is missing or outside the filestore.')
        with file.open('rb') as handle:
            result['files'][name] = hashlib.file_digest(handle, 'sha256').hexdigest()
    return result


def assert_unchanged(cr, data_dir, database, expected):
    actual = snapshot(cr, data_dir, database, expected)
    if actual != expected:
        changed = [table for table in expected['tables'] if expected['tables'][table] != actual['tables'].get(table)]
        raise RuntimeError('Client integrity check failed: %s. Review changes; no automatic restoration.' %
                           (', '.join(changed) or 'attachment content'))
