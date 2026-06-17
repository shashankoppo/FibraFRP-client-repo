"""
SaaS Module Upgrade Tracking
=============================
Tracks all version upgrades for data integrity and rollback capability.
Ensures zero data loss and enables safe version management.
"""

from odoo import fields, models, api
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)


class ELSXSaasUpgradeLog(models.Model):
    """Track all module upgrades with complete audit trail"""
    _name = 'elsx.saas.upgrade.log'
    _description = 'SaaS Module Upgrade Log'
    _order = 'upgrade_date desc, id desc'
    _rec_name = 'upgrade_id'

    # Core Fields
    upgrade_id = fields.Char(
        string='Upgrade ID',
        readonly=True,
        copy=False,
        index=True
    )
    from_version = fields.Char(
        string='From Version',
        readonly=True,
        required=True
    )
    to_version = fields.Char(
        string='To Version',
        readonly=True,
        required=True
    )
    upgrade_date = fields.Datetime(
        string='Upgrade Date',
        readonly=True,
        default=lambda self: fields.Datetime.now()
    )

    # Status Fields
    status = fields.Selection([
        ('preparing', 'Preparing'),
        ('pre_checks', 'Running Pre-Checks'),
        ('backing_up', 'Backing Up Data'),
        ('migrating', 'Migrating Data'),
        ('post_checks', 'Running Post-Checks'),
        ('completed', 'Completed Successfully'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back')
    ], string='Status', readonly=True, default='preparing', index=True)

    # Tracking
    total_records_migrated = fields.Integer(
        string='Total Records Migrated',
        readonly=True
    )
    models_affected = fields.Text(
        string='Models Affected',
        help='JSON list of affected model names'
    )
    duration_minutes = fields.Float(
        string='Duration (minutes)',
        readonly=True
    )

    # Validation
    pre_check_results = fields.Text(
        string='Pre-Check Results',
        readonly=True,
        help='JSON with all pre-upgrade validation results'
    )
    post_check_results = fields.Text(
        string='Post-Check Results',
        readonly=True,
        help='JSON with all post-upgrade validation results'
    )

    # Backup & Rollback
    backup_location = fields.Char(
        string='Backup Location',
        readonly=True,
        help='Path to backup file'
    )
    backup_size_mb = fields.Float(
        string='Backup Size (MB)',
        readonly=True
    )
    backup_verified = fields.Boolean(
        string='Backup Verified',
        readonly=True
    )
    can_rollback = fields.Boolean(
        string='Can Rollback',
        readonly=True,
        compute='_compute_can_rollback'
    )

    # Log Details
    upgrade_log = fields.Text(
        string='Upgrade Log',
        readonly=True,
        help='Complete upgrade process log'
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
        help='Error details if upgrade failed'
    )
    created_by = fields.Many2one(
        'res.users',
        string='Initiated By',
        readonly=True,
        default=lambda self: self.env.user
    )

    # Rollback Info
    rolled_back_date = fields.Datetime(
        string='Rolled Back Date',
        readonly=True
    )
    rollback_reason = fields.Text(
        string='Rollback Reason',
        readonly=True
    )

    @api.depends('backup_location', 'backup_verified', 'status')
    def _compute_can_rollback(self):
        """Check if upgrade can be rolled back"""
        for record in self:
            record.can_rollback = (
                record.status == 'completed' and
                record.backup_verified and
                record.backup_location
            )

    @api.model
    def log_upgrade_start(self, from_version, to_version, affected_models):
        """Log start of upgrade process"""
        upgrade_log = self.create({
            'upgrade_id': self._generate_upgrade_id(),
            'from_version': from_version,
            'to_version': to_version,
            'models_affected': json.dumps(affected_models),
            'status': 'preparing',
            'created_by': self.env.user.id,
        })
        _logger.info(f'Upgrade started: {upgrade_log.upgrade_id}')
        return upgrade_log

    @api.model
    def _generate_upgrade_id(self):
        """Generate unique upgrade ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f'UPGRADE_{timestamp}'

    def log_pre_check_results(self, results):
        """Update with pre-check validation results"""
        self.pre_check_results = json.dumps(results)
        self.status = 'pre_checks'
        _logger.info(f'Pre-checks completed for {self.upgrade_id}')

    def log_backup_created(self, backup_path, size_mb, verified=True):
        """Record backup creation"""
        self.backup_location = backup_path
        self.backup_size_mb = size_mb
        self.backup_verified = verified
        self.status = 'backing_up'
        _logger.info(f'Backup created for {self.upgrade_id}: {backup_path}')

    def log_migration_progress(self, records_migrated):
        """Update migration progress"""
        self.total_records_migrated = records_migrated
        self.status = 'migrating'

    def log_post_check_results(self, results):
        """Update with post-upgrade validation results"""
        self.post_check_results = json.dumps(results)
        self.status = 'post_checks'
        _logger.info(f'Post-checks completed for {self.upgrade_id}')

    def mark_completed(self, duration_minutes):
        """Mark upgrade as successfully completed"""
        self.status = 'completed'
        self.duration_minutes = duration_minutes
        _logger.info(f'Upgrade completed: {self.upgrade_id} ({duration_minutes:.2f} min)')

    def mark_failed(self, error_message):
        """Mark upgrade as failed"""
        self.status = 'failed'
        self.error_message = error_message
        _logger.error(f'Upgrade failed: {self.upgrade_id}\nError: {error_message}')

    def action_rollback(self, reason='Manual rollback requested'):
        """Show rollback guidance without mutating production state.

        Database rollback must be performed from the controlled server shell
        using the encrypted backup restore script. Marking the log as
        rolled_back from the UI would be misleading because no database or
        filestore restore happens here.
        """
        if not self.can_rollback:
            raise ValueError('Cannot rollback: No valid backup available')

        _logger.warning(
            'Rollback requested from UI for %s. Backup path was shown; no restore was executed. Reason: %s',
            self.upgrade_id,
            reason,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Manual restore required',
                'message': (
                    'Use the encrypted restore script from the server shell. '
                    'Backup path: %s'
                ) % self.backup_location,
                'type': 'warning',
                'sticky': True,
            },
        }


class ELSXSaasVersionCheck(models.Model):
    """Track installed versions and compatibility"""
    _name = 'elsx.saas.version.check'
    _description = 'SaaS Module Version Check'
    _order = 'check_date desc'

    module_name = fields.Char(
        string='Module Name',
        readonly=True,
        default='elsx_saas'
    )
    current_version = fields.Char(
        string='Current Version',
        readonly=True
    )
    database_version = fields.Char(
        string='Database Version',
        readonly=True,
        help='Version when database was last updated'
    )
    is_compatible = fields.Boolean(
        string='Compatible',
        readonly=True
    )
    check_date = fields.Datetime(
        string='Check Date',
        readonly=True,
        default=lambda self: fields.Datetime.now()
    )
    compatibility_issues = fields.Text(
        string='Compatibility Issues',
        readonly=True
    )

    @api.model
    def check_version_compatibility(self, current_version, database_version):
        """Check if versions are compatible"""
        check = self.create({
            'current_version': current_version,
            'database_version': database_version,
        })

        # Define compatibility matrix
        compatibility_map = {
            '19.0.2.0.0': ['19.0.1.0.0', '19.0.1.1.0', '19.0.1.2.0', '19.0.1.2.1'],
            '19.0.1.2.1': ['19.0.1.0.0', '19.0.1.1.0', '19.0.1.2.0'],
        }

        compatible_versions = compatibility_map.get(current_version, [])
        is_compatible = database_version in compatible_versions or current_version == database_version

        check.is_compatible = is_compatible

        if not is_compatible:
            check.compatibility_issues = (
                f'Database version {database_version} may not be compatible '
                f'with current version {current_version}. '
                f'Compatible versions: {", ".join(compatible_versions)}'
            )

        return check
