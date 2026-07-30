from . import models


def _setup_module(env):
    # ELSxGlobal: disabled MuK theme bootstrap so native Odoo/rebrand assets stay authoritative.
    return None


def _uninstall_cleanup(env):
    env['res.config.settings']._reset_theme_color_assets()
