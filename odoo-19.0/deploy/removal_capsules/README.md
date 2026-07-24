# Removal capsules

This directory is not part of Odoo's configured `addons_path`.

`elsx_saas` is retained here temporarily so an existing production database
can load its old model registry long enough for Odoo's normal uninstall process
to remove the retired module. The startup updater uses it only after creating
and verifying an encrypted database backup. Normal Odoo startup cannot discover,
install, or load this capsule.

The capsule can be deleted in a later release after every production database
reports `elsx_saas` as `uninstalled`.
