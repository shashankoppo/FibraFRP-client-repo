# Deployment

Ubuntu and Alpine use `bash deploy-prod.sh` from `odoo-19.0` to upgrade installed
addons through the encrypted-backup release gate. Ordinary container startup
does not perform schema upgrades. Fresh databases use `bash deploy-new.sh` with
this addon explicitly included in `NEW_INSTALL_MODULES`.

After deployment, verify that Settings, Users and Companies open their native
actions, Administrator can manage user permissions, and Apps requires its
separate password. Test wrong password, unlock, relock, expiry and direct locked
module-management RPCs. Safe Module Change remains absent.

Use `?debug=1` or Odoo's Activate Developer Mode command to expose native
Groups, Access Rights, and Record Rules technical buttons.
