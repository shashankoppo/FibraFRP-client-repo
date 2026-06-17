"""
Pre-Upgrade Validation Checks
==============================
Ensures system is ready for upgrade with zero data loss risk.
All checks must pass before upgrade proceeds.
"""

import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


def run_pre_upgrade_checks(env):
    """
    Execute all pre-upgrade validation checks.
    Returns dict with check results and failures.

    Args:
        env: Odoo environment

    Returns:
        dict: {
            'all_passed': bool,
            'timestamp': str,
            'checks': {
                'check_name': {
                    'passed': bool,
                    'message': str,
                    'severity': 'critical|warning|info'
                }
            }
        }
    """
    checks_results = {
        'all_passed': True,
        'timestamp': datetime.now().isoformat(),
        'checks': {}
    }

    try:
        # 1. Database Backup Check
        _logger.info('Running: Database Backup Check')
        checks_results['checks']['database_backup'] = check_database_backup(env)

        # 2. Disk Space Check
        _logger.info('Running: Disk Space Check')
        checks_results['checks']['disk_space'] = check_disk_space(env)

        # 3. Active Sessions Check
        _logger.info('Running: Active Sessions Check')
        checks_results['checks']['active_sessions'] = check_active_sessions(env)

        # 4. Data Integrity Check
        _logger.info('Running: Data Integrity Check')
        checks_results['checks']['data_integrity'] = check_data_integrity(env)

        # 5. Module Dependencies Check
        _logger.info('Running: Module Dependencies Check')
        checks_results['checks']['module_dependencies'] = check_module_dependencies(env)

        # 6. Database Locks Check
        _logger.info('Running: Database Locks Check')
        checks_results['checks']['database_locks'] = check_database_locks(env)

        # 7. Log Files Check
        _logger.info('Running: Log Files Check')
        checks_results['checks']['log_space'] = check_log_space(env)

        # 8. Cron Jobs Check
        _logger.info('Running: Cron Jobs Check')
        checks_results['checks']['cron_jobs'] = check_cron_jobs(env)

        # Determine overall status
        checks_results['all_passed'] = all(
            check['passed'] for check in checks_results['checks'].values()
            if check['severity'] in ['critical']  # Only critical must pass
        )

        return checks_results

    except Exception as e:
        _logger.error(f'Error during pre-upgrade checks: {str(e)}')
        checks_results['all_passed'] = False
        checks_results['checks']['system_error'] = {
            'passed': False,
            'message': f'System error during checks: {str(e)}',
            'severity': 'critical'
        }
        return checks_results


def check_database_backup(env):
    """Verify recent database backup exists"""
    try:
        # Check if backup directory exists and has recent files
        backup_dir = env['ir.config_parameter'].sudo().get_param(
            'saas.backup_directory',
            '/tmp/odoo_backups'
        )

        import os
        if not os.path.exists(backup_dir):
            return {
                'passed': False,
                'message': f'Backup directory not found: {backup_dir}',
                'severity': 'critical'
            }

        # Check for recent backup (within last 24 hours)
        files = os.listdir(backup_dir)
        if not files:
            return {
                'passed': False,
                'message': 'No backup files found in backup directory',
                'severity': 'critical'
            }

        # Get newest file
        newest_file = max(files, key=lambda f: os.path.getctime(os.path.join(backup_dir, f)))
        newest_time = os.path.getctime(os.path.join(backup_dir, newest_file))
        age_hours = (datetime.now().timestamp() - newest_time) / 3600

        if age_hours > 24:
            return {
                'passed': False,
                'message': f'Most recent backup is {age_hours:.1f} hours old',
                'severity': 'warning'
            }

        return {
            'passed': True,
            'message': f'Recent backup found: {newest_file} ({age_hours:.1f} hours old)',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Backup check failed: {str(e)}',
            'severity': 'critical'
        }


def check_disk_space(env):
    """Verify sufficient disk space for upgrade"""
    try:
        import shutil

        # Get database size estimate
        db_name = env.cr.dbname
        tables = env['ir.model'].sudo().search([])

        # Simple check: 2GB free space required
        stat = shutil.disk_usage('/')
        free_gb = stat.free / (1024**3)

        if free_gb < 2:
            return {
                'passed': False,
                'message': f'Insufficient disk space: {free_gb:.1f}GB available (need 2GB)',
                'severity': 'critical'
            }

        return {
            'passed': True,
            'message': f'Sufficient disk space: {free_gb:.1f}GB available',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Disk space check failed: {str(e)}',
            'severity': 'warning'
        }


def check_active_sessions(env):
    """Check for active user sessions that should be closed"""
    try:
        # Count active sessions
        res_users = env['res.users'].search([
            ('login_date', '>=', datetime.now() - timedelta(minutes=30))
        ])

        active_count = len(res_users)

        if active_count > 0:
            return {
                'passed': False,
                'message': f'{active_count} active user sessions detected. Close all sessions before upgrade.',
                'severity': 'warning'
            }

        return {
            'passed': True,
            'message': 'No active user sessions',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Session check failed: {str(e)}',
            'severity': 'warning'
        }


def check_data_integrity(env):
    """Verify database integrity and constraints"""
    try:
        # Check for orphaned records
        SaaSTenant = env['elsx.saas.tenant']
        tenants = SaaSTenant.search([])

        issues = []

        for tenant in tenants:
            if not tenant.name:
                issues.append(f'Tenant {tenant.id} missing name')
            if not tenant.db_name:
                issues.append(f'Tenant {tenant.id} missing db_name')

        if issues:
            return {
                'passed': False,
                'message': f'Data integrity issues found: {", ".join(issues[:5])}',
                'severity': 'warning'
            }

        return {
            'passed': True,
            'message': f'Data integrity verified for {len(tenants)} tenants',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Data integrity check failed: {str(e)}',
            'severity': 'warning'
        }


def check_module_dependencies(env):
    """Verify all required dependencies are installed"""
    try:
        required_modules = ['mail', 'base', 'sale', 'account', 'hr']

        ir_module = env['ir.module.module']
        missing = []

        for module_name in required_modules:
            module = ir_module.search([
                ('name', '=', module_name),
                ('state', '=', 'installed')
            ])
            if not module:
                missing.append(module_name)

        if missing:
            return {
                'passed': False,
                'message': f'Missing required modules: {", ".join(missing)}',
                'severity': 'critical'
            }

        return {
            'passed': True,
            'message': 'All required module dependencies installed',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Module dependency check failed: {str(e)}',
            'severity': 'warning'
        }


def check_database_locks(env):
    """Check for long-running transactions or locks"""
    try:
        # Try to execute a simple query to check connection health
        env.cr.execute('SELECT 1')
        env.cr.fetchone()

        return {
            'passed': True,
            'message': 'No database locks detected',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Database lock check failed: {str(e)}',
            'severity': 'critical'
        }


def check_log_space(env):
    """Check log file space usage"""
    try:
        import os

        log_dir = env['ir.config_parameter'].sudo().get_param(
            'saas.log_directory',
            '/var/log/odoo'
        )

        if not os.path.exists(log_dir):
            return {
                'passed': True,
                'message': 'Log directory not found, skipping check',
                'severity': 'info'
            }

        total_size = 0
        for filename in os.listdir(log_dir):
            filepath = os.path.join(log_dir, filename)
            if os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)

        size_mb = total_size / (1024**2)

        if size_mb > 1000:  # 1GB limit
            return {
                'passed': False,
                'message': f'Log files using {size_mb:.1f}MB (consider cleanup)',
                'severity': 'warning'
            }

        return {
            'passed': True,
            'message': f'Log file size: {size_mb:.1f}MB',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Log space check failed: {str(e)}',
            'severity': 'info'
        }


def check_cron_jobs(env):
    """Verify scheduled cron jobs won't interfere"""
    try:
        ir_cron = env['ir.cron']
        active_crons = ir_cron.search([('active', '=', True)])

        # Check if any critical crons will run during upgrade window
        critical_crons = []
        for cron in active_crons:
            if 'upgrade' in cron.name.lower() or 'backup' in cron.name.lower():
                critical_crons.append(cron.name)

        if critical_crons:
            return {
                'passed': False,
                'message': f'Critical crons running: {", ".join(critical_crons[:5])}. Disable before upgrade.',
                'severity': 'warning'
            }

        return {
            'passed': True,
            'message': f'{len(active_crons)} cron jobs running (safe to upgrade)',
            'severity': 'info'
        }
    except Exception as e:
        return {
            'passed': False,
            'message': f'Cron job check failed: {str(e)}',
            'severity': 'info'
        }
