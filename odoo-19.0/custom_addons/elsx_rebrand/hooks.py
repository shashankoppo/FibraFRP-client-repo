# -*- coding: utf-8 -*-


def post_init_hook(env):
    env["ir.config_parameter"].sudo()._elsx_apply_ui_rebrand()