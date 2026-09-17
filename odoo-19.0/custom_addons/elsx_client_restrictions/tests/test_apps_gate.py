from types import SimpleNamespace
from unittest.mock import patch

from lxml import html
from passlib.hash import pbkdf2_sha512

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .. import apps_gate


@tagged("post_install", "-at_install")
class TestAppsGate(TransactionCase):
    def test_ticket_is_bound_to_user_database_time_and_password(self):
        ticket = apps_gate.unlock_ticket(2, "test_database")
        self.assertTrue(apps_gate.ticket_valid(ticket, 2, "test_database"))
        self.assertFalse(apps_gate.ticket_valid(ticket, 1, "test_database"))
        self.assertFalse(apps_gate.ticket_valid(ticket, 2, "other_database"))
        self.assertFalse(apps_gate.ticket_valid(dict(ticket, expires=1), 2, "test_database"))
        self.assertFalse(apps_gate.ticket_valid(dict(ticket, version="forged"), 2, "test_database"))
        self.assertFalse(apps_gate.ticket_valid(None, 2, "test_database"))
        with patch.object(apps_gate, "password_hash", return_value="rotated"):
            self.assertFalse(apps_gate.ticket_valid(ticket, 2, "test_database"))

    def test_no_admin_or_context_bypass_for_module_mutations(self):
        session = SimpleNamespace(uid=1, get=lambda key: None)
        locked = SimpleNamespace(session=session, db=self.env.cr.dbname)
        module = self.env.ref("base.module_base").sudo().with_context(elsx_apps_unlocked=True)
        with patch.object(apps_gate, "request", locked):
            with self.assertRaises(AccessError):
                module.write({"sequence": module.sequence})
            # Native Settings reads and business records do not need the Apps unlock.
            self.assertTrue(module.read(["name"]))
            self.env["res.config.settings"].default_get(["company_id"])
            self.env["res.partner"].create({"name": "Apps guard test partner"})

    def test_offline_maintenance_is_not_blocked(self):
        with patch.object(apps_gate, "request", None):
            self.env.ref("base.module_base").write({"sequence": 100})

    def test_malformed_password_hash_fails_closed(self):
        with patch.object(apps_gate, "password_hash", return_value="invalid"):
            self.assertFalse(apps_gate.password_matches("test"))


@tagged("post_install", "-at_install")
class TestAppsGateHTTP(HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")
        self.opener.headers["Connection"] = "close"
        self.hash_patch = patch.object(apps_gate, "password_hash", return_value=
                                       pbkdf2_sha512.using(rounds=1000).hash("test-apps-only"))
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)
        self.env["ir.config_parameter"].search([
            ("key", "=", "elsx.apps_gate.attempts.%s" % self.session.uid)]).unlink()
        self.env.flush_all()

    def rpc(self, path, **params):
        return self.url_open(path, json={"jsonrpc": "2.0", "id": 1, "params": params}).json()

    def csrf(self):
        page = self.url_open("/elsx/apps/unlock")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers["Cache-Control"], "no-store")
        return html.fromstring(page.content).xpath("//input[@name='csrf_token']/@value")[0]

    def test_apps_action_and_direct_rpc_locked_settings_unchanged(self):
        for action in ("apps", "base.open_module_tree", self.env.ref("base.open_module_tree").id):
            result = self.rpc("/web/action/load", action_id=action)["result"]
            self.assertEqual(result["url"], "/elsx/apps/unlock")
        result = self.rpc("/web/dataset/call_kw", model="ir.module.module", method="search_read",
                          args=[[]], kwargs={"fields": ["name"], "limit": 1,
                                           "context": {"elsx_apps_unlocked": True}})
        self.assertIn("error", result)
        result = self.rpc("/web/action/load", action_id="base_setup.action_general_configuration")
        self.assertEqual(result["result"]["res_model"], "res.config.settings")
        result = self.rpc("/web/dataset/call_kw", model="res.config.settings", method="get_views",
                          args=[], kwargs={"views": [[False, "form"]]})
        self.assertIn("result", result)

    def test_password_unlock_relock_and_guard_cannot_be_removed(self):
        response = self.url_open("/elsx/apps/unlock", data={"password": "wrong", "csrf_token": self.csrf()})
        self.assertEqual(response.status_code, 403)
        token = self.csrf()
        response = self.url_open("/elsx/apps/unlock", data={"password": "test-apps-only", "csrf_token": token},
                                 allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.rpc("/web/action/load", action_id="apps")["result"]["res_model"], "ir.module.module")
        result = self.rpc("/web/dataset/call_kw", model="ir.module.module", method="search_read",
                          args=[[('name', '=', 'base')]], kwargs={"fields": ["name"]})
        self.assertEqual(result["result"][0]["name"], "base")
        result = self.rpc("/web/dataset/call_kw", model="ir.module.module", method="write",
                          args=[[self.env.ref("base.module_elsx_client_restrictions").id], {"state": "to remove"}], kwargs={})
        self.assertIn("error", result)
        self.url_open("/elsx/apps/lock", data={"csrf_token": token})
        self.assertEqual(self.rpc("/web/action/load", action_id="apps")["result"]["type"], "ir.actions.act_url")

    def test_attempt_limit_survives_new_browser_session(self):
        token = self.csrf()
        for _ in range(apps_gate.MAX_ATTEMPTS):
            self.assertEqual(self.url_open("/elsx/apps/unlock", data={"password": "wrong", "csrf_token": token}).status_code, 403)
        self.authenticate("admin", "admin")
        response = self.url_open("/elsx/apps/unlock", data={"password": "test-apps-only", "csrf_token": self.csrf()})
        self.assertEqual(response.status_code, 429)

    def test_unlock_does_not_grant_apps_to_ordinary_user(self):
        self.env["res.users"].create({"name": "Apps test employee", "login": "apps_test_employee",
                                     "group_ids": [Command.set([self.env.ref("base.group_user").id])]})
        self.authenticate("apps_test_employee", "test")
        self.assertEqual(self.url_open("/elsx/apps/unlock").status_code, 403)

    def test_unlock_requires_csrf(self):
        self.assertEqual(self.url_open("/elsx/apps/unlock", data={"password": "test-apps-only"}).status_code, 400)
