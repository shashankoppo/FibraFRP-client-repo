from odoo import models, fields, api
import subprocess
import logging
import sys

_logger = logging.getLogger(__name__)

class ELSXSaasTenant(models.Model):
    _name = 'elsx.saas.tenant'
    _description = 'SaaS Tenant Database'

    name = fields.Char('Subdomain', required=True)
    db_name = fields.Char('Database Name', compute='_compute_db_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('provisioning', 'Provisioning'),
        ('active', 'Active'),
        ('suspended', 'Suspended')
    ], default='draft')
    admin_email = fields.Char('Admin Email')
    plan = fields.Selection([
        ('starter', 'ELSX Starter'),
        ('luxury', 'ELSX Luxury'),
        ('quantum', 'ELSX Quantum')
    ], default='starter')
    
    # Premium Resource Quotas
    storage_quota_gb = fields.Integer('Storage Quota (GB)', default=5)
    max_users = fields.Integer('Max Users', default=10)
    custom_domain = fields.Char('Custom Domain')

    @api.depends('name')
    def _compute_db_name(self):
        for record in self:
            if record.name:
                record.db_name = f"elsx_{record.name.lower()}"

    def action_provision(self):
        self.ensure_one()
        self.state = 'provisioning'
        self._compute_db_name()
        _logger.info(f"Starting provisioning for tenant: {self.db_name}")

        # Path to odoo-bin (using relative paths where possible or config)
        #Ideally this should be fetched from configuration parameters
        python_exe = sys.executable 
        odoo_bin = "c:\\Users\\Shashank patel\\Desktop\\odoov0\\odoo-bin"
        config_file = "c:\\Users\\Shashank patel\\Desktop\\odoov0\\local_odoo.conf"

        try:
            # check if db exists first
            if self._check_db_exists(self.db_name):
                 _logger.warning(f"Database {self.db_name} already exists. Skipping creation.")
                 self.state = 'active'
                 return

            # Command to create database and install base + elsx_rebrand + oca_web + oca_server_brand
            # -d: database name
            # -i: modules to install
            # --stop-after-init: stop after the operation is done
            cmd = [
                python_exe, odoo_bin,
                "-c", config_file,
                "-d", self.db_name,
                "-i", "base,elsx_rebrand,web_responsive,mail_debranding,elsx_evolution,elsx_whatsapp_marketing,elsx_ai_marketing,elsx_blockchain_ledger,elsx_security,contacts,crm,sale,account",
                "--stop-after-init",
                "--no-database-list" # Security best practice
            ]

            _logger.info(f"Executing: {' '.join(cmd)}")
            
            # Run the command
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(timeout=600) # Increased timeout for installation

            if process.returncode == 0:
                # Double check verification
                if self._check_db_exists(self.db_name):
                    self.state = 'active'
                    _logger.info(f"Successfully provisioned: {self.db_name}")
                    
                    # Log to ELSX Blockchain Ledger
                    try:
                        self.env['elsx.blockchain.log'].create({
                            'model_name': 'elsx.saas.tenant',
                            'res_id': self.id,
                            'operation': 'create',
                            'data_snapshot': f"Provisioned DB: {self.db_name}, Plan: {self.plan}, Admin: {self.admin_email}",
                            'previous_hash': 'SAAS_PROVISIONING',
                            'current_hash': 'PENDING_VERIFICATION' # Will be computed by ledger logic
                        })
                    except Exception as e:
                        _logger.warning(f"Blockchain logging failed for {self.db_name}: {e}")
                else:
                     self.state = 'draft'
                     _logger.error(f"Provisioning reported success but DB not found: {self.db_name}")
            else:
                _logger.error(f"Provisioning Failed for {self.db_name}: {stderr}")
                self.state = 'draft'

        except subprocess.TimeoutExpired:
             _logger.error(f"Provisioning timed out for {self.db_name}")
             self.state = 'draft'
             if process:
                 process.kill()
        except Exception as e:
            _logger.error(f"Provisioning Exception: {e}")
            self.state = 'draft'

    def _check_db_exists(self, db_name):
        # This is a placeholder. In a real scenario we'd query the postgres table or list_dbs
        # For now, we assume if the command succeeded, it exists. 
        # But we can try to connect to it.
        try:
            # checking via psutil or file system if needed, but for now we rely on return code
            return False 
        except:
            return False
