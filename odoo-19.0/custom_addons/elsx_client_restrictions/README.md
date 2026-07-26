# ELSX Native Administration Cleanup

This technical compatibility addon removes retired ELSX access restrictions.
It does not replace Odoo access control.

- Settings, Users, Companies, Apps, groups, access rights, and record rules use
  native Odoo 19 Community behavior.
- The built-in Administrator retains System Administration and Access Rights.
- Legacy Apps passwords, secret URLs, module guards, safety menus, custom
  branding views, and restriction groups are removed.
- Client users, companies, business records, attachments, and functional
  modules are not deleted or rewritten.

Odoo 19 has a newer native Users form than earlier Odoo versions. Enable
Developer Mode when the Groups, Access Rights, and Record Rules technical
buttons are needed.
