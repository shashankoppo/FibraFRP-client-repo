"""Apps-only step-up authentication. No business records or login passwords change."""
import hashlib
import os
import time

from passlib.hash import pbkdf2_sha512

from odoo import _
from odoo.exceptions import AccessError
from odoo.http import request


DEFAULT_PASSWORD_HASH = "$pbkdf2-sha512$600000$2zvHOGestZYyptSaU.pdaw$ze61np0m8Ly4X7RMxFTn94pxw08Y1Rnss1Q0mhzyIM4fTBGXtZwJ6A/SeX9sWLxQtUFgAUE9.hk7znQ/BXuVaw"
SESSION_KEY = "elsx_apps_unlock"
UNLOCK_SECONDS = 15 * 60
ATTEMPT_WINDOW = 5 * 60
MAX_ATTEMPTS = 6


def password_hash():
    return os.environ.get("ELSX_APPS_PASSWORD_HASH") or DEFAULT_PASSWORD_HASH


def password_matches(password):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        return pbkdf2_sha512.verify(password, password_hash())
    except (TypeError, ValueError):
        return False


def unlock_ticket(uid, database):
    return {"uid": uid, "database": database, "expires": time.time() + UNLOCK_SECONDS,
            "version": hashlib.sha256(password_hash().encode()).hexdigest()}


def ticket_valid(ticket, uid, database):
    if not isinstance(ticket, dict):
        return False
    expires = ticket.get("expires")
    return bool(uid and ticket.get("uid") == uid and ticket.get("database") == database
                and isinstance(expires, (int, float)) and time.time() < expires <= time.time() + UNLOCK_SECONDS
                and ticket.get("version") == hashlib.sha256(password_hash().encode()).hexdigest())


def is_unlocked():
    return bool(request and request.session.uid
                and ticket_valid(request.session.get(SESSION_KEY), request.session.uid, request.db))


def require_unlocked():
    # Offline maintenance has its own installed-only deployment guard. Never trust RPC context flags.
    if request and not is_unlocked():
        raise AccessError(_("Apps is locked. Open Apps and enter the Apps password first."))


def protected_model(model):
    return bool(model and (model.startswith("ir.module.") or model.startswith("base.module.")
                           or model == "base.import.module"))


def claim_attempt(registry, uid):
    """Persist attempts separately so HTTP rollback/new sessions cannot reset the limit."""
    bucket = int(time.time()) // ATTEMPT_WINDOW
    key = "elsx.apps_gate.attempts.%s" % uid
    with registry.cursor() as cr:
        cr.execute("""
            INSERT INTO ir_config_parameter (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value =
                CASE WHEN split_part(ir_config_parameter.value, ':', 1) = %s
                     THEN %s || ':' || (split_part(ir_config_parameter.value, ':', 2)::integer + 1)::text
                     ELSE EXCLUDED.value END
            RETURNING split_part(value, ':', 2)::integer
        """, [key, "%s:1" % bucket, str(bucket), str(bucket)])
        count = cr.fetchone()[0]
        cr.commit()
    return count <= MAX_ATTEMPTS
