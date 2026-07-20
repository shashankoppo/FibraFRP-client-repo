# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api
from odoo.addons.elsx_whatsapp_core.hooks import (
    sync_legacy_ownership,
    sync_shell_schema_aliases,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sync_shell_schema_aliases(env)
    sync_legacy_ownership(env)
