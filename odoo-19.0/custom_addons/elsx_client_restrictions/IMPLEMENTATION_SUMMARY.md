# Implementation Summary

The module now acts as a compatibility layer:

- `ir.ui.menu.load_menus()` delegates directly to Odoo.
- `ir.module.module.update_list()` delegates directly to Odoo.
- `/action-39` redirects old bookmarks to the normal Apps action.
- XML records are kept only so existing database references keep upgrading.

Do not put product access rules, time-based access logic, Apps menu override logic, or
automatic upgrade logic in this addon.
