# ELSX Apps Access and Native Administration

This technical compatibility addon removes retired ELSX access restrictions.
It does not replace Odoo access control.

- Settings, Users, Companies, groups, access rights, and record rules use
  native Odoo 19 Community behavior.
- The built-in Administrator retains System Administration and Access Rights.
- Legacy Apps passwords, secret URLs, module guards, safety menus, custom
  branding views, and restriction groups are removed.
- Apps uses native Odoo views and administrator permissions after a separate
  session password unlock. The password is hashed, attempts are throttled,
  and the unlock expires after 15 minutes or logout. No administrator bypass.
- This guard has no UI disable switch and cannot remove itself through Apps.
  An operator with host/database/custom-code control is outside its boundary.
- The gate does not modify client records, consent or ERP login credentials.
  Existing metadata cleanup may rebuild generated assets, not client attachments.
- Install this addon explicitly on a fresh database. Production deployment
  refuses a missing guard instead of silently installing it.

See [deployment quickstart](../../DEPLOYMENT_QUICKSTART.md) for permanent commands.

Odoo 19 has a newer native Users form than earlier Odoo versions. Enable
Developer Mode when the Groups, Access Rights, and Record Rules technical
buttons are needed.
