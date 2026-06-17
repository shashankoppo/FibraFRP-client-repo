"""
Data Migration Helpers
======================
Safe utilities for migrating data during version upgrades.
All operations are transactional and reversible.
"""

import logging
import json
from datetime import datetime
from copy import deepcopy

_logger = logging.getLogger(__name__)


class DataMigrationHelper:
    """Safe data transformation utility"""

    def __init__(self, env):
        self.env = env
        self.migration_log = []
        self.migration_start = datetime.now()

    def log_migration(self, action, details):
        """Log migration action"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details
        }
        self.migration_log.append(log_entry)
        _logger.info(f'Migration: {action} - {details}')

    def get_migration_log(self):
        """Return complete migration log as JSON"""
        return json.dumps(self.migration_log, indent=2)

    def migrate_field_values(self, model_name, field_mapping):
        """
        Safely rename or transform field values.

        Args:
            model_name: str - Model to migrate
            field_mapping: dict - {old_field: new_field}

        Returns:
            dict: {migrated: int, failed: int, errors: []}
        """
        results = {'migrated': 0, 'failed': 0, 'errors': []}

        try:
            Model = self.env[model_name]
            records = Model.search([])

            for record in records:
                try:
                    values = {}
                    for old_field, new_field in field_mapping.items():
                        if hasattr(record, old_field):
                            values[new_field] = getattr(record, old_field)

                    if values:
                        record.write(values)
                        results['migrated'] += 1
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(f'Record {record.id}: {str(e)}')

            self.log_migration(
                'field_migration',
                f'{model_name}: {results["migrated"]} records migrated'
            )
            return results

        except Exception as e:
            results['errors'].append(str(e))
            self.log_migration('field_migration_error', f'{model_name}: {str(e)}')
            return results

    def migrate_selection_values(self, model_name, field_name, value_mapping):
        """
        Safely map old selection values to new ones.

        Args:
            model_name: str - Model to migrate
            field_name: str - Field to migrate
            value_mapping: dict - {old_value: new_value}

        Returns:
            dict: {migrated: int, failed: int}
        """
        results = {'migrated': 0, 'failed': 0}

        try:
            Model = self.env[model_name]

            for old_value, new_value in value_mapping.items():
                records = Model.search([(field_name, '=', old_value)])
                records.write({field_name: new_value})
                results['migrated'] += len(records)

            self.log_migration(
                'selection_migration',
                f'{model_name}.{field_name}: {results["migrated"]} records updated'
            )
            return results

        except Exception as e:
            results['failed'] = 1
            self.log_migration(
                'selection_migration_error',
                f'{model_name}.{field_name}: {str(e)}'
            )
            return results

    def backup_records(self, model_name, domain=None):
        """
        Backup records before migration.

        Args:
            model_name: str - Model to backup
            domain: list - Optional search domain

        Returns:
            dict: Backup data with timestamp
        """
        try:
            Model = self.env[model_name]
            records = Model.search(domain or [])

            backup = {
                'timestamp': datetime.now().isoformat(),
                'model': model_name,
                'count': len(records),
                'records': []
            }

            for record in records:
                backup['records'].append({
                    'id': record.id,
                    'data': record.read([])[0] if record.read([]) else {}
                })

            self.log_migration(
                'backup_created',
                f'{model_name}: {len(records)} records backed up'
            )
            return backup

        except Exception as e:
            self.log_migration('backup_error', f'{model_name}: {str(e)}')
            return None

    def restore_records(self, backup_data):
        """
        Restore records from backup.

        Args:
            backup_data: dict - Backup created by backup_records()

        Returns:
            dict: {restored: int, failed: int}
        """
        results = {'restored': 0, 'failed': 0}

        try:
            Model = self.env[backup_data['model']]

            for record_data in backup_data['records']:
                try:
                    record = Model.browse(record_data['id'])
                    if record.exists():
                        # Update existing record
                        record.write(record_data['data'])
                    results['restored'] += 1
                except Exception as e:
                    results['failed'] += 1
                    _logger.error(f'Restore failed for {record_data["id"]}: {str(e)}')

            self.log_migration(
                'restore_completed',
                f'{backup_data["model"]}: {results["restored"]} records restored'
            )
            return results

        except Exception as e:
            self.log_migration('restore_error', f'Backup restore failed: {str(e)}')
            return results

    def create_missing_records(self, model_name, record_templates):
        """
        Create records with default data if they don't exist.

        Args:
            model_name: str - Model to create records for
            record_templates: list - [{name: 'value', ...}, ...]

        Returns:
            dict: {created: int, skipped: int}
        """
        results = {'created': 0, 'skipped': 0}

        try:
            Model = self.env[model_name]

            for template in record_templates:
                search_domain = [('name', '=', template.get('name'))]
                existing = Model.search(search_domain)

                if not existing:
                    Model.create(template)
                    results['created'] += 1
                else:
                    results['skipped'] += 1

            self.log_migration(
                'records_created',
                f'{model_name}: {results["created"]} created, {results["skipped"]} skipped'
            )
            return results

        except Exception as e:
            self.log_migration('create_records_error', f'{model_name}: {str(e)}')
            return results

    def validate_migrated_data(self, model_name, field_checks):
        """
        Validate data after migration.

        Args:
            model_name: str - Model to validate
            field_checks: dict - {field: validation_function}

        Returns:
            dict: {valid: int, invalid: int, issues: []}
        """
        results = {'valid': 0, 'invalid': 0, 'issues': []}

        try:
            Model = self.env[model_name]
            records = Model.search([])

            for record in records:
                for field, validator in field_checks.items():
                    try:
                        value = getattr(record, field)
                        if not validator(value):
                            results['invalid'] += 1
                            results['issues'].append(
                                f'Record {record.id}.{field}: invalid value {value}'
                            )
                    except Exception as e:
                        results['invalid'] += 1
                        results['issues'].append(
                            f'Record {record.id}.{field}: {str(e)}'
                        )

                results['valid'] += 1

            self.log_migration(
                'validation_completed',
                f'{model_name}: {results["valid"]} valid, {results["invalid"]} invalid'
            )
            return results

        except Exception as e:
            self.log_migration('validation_error', f'{model_name}: {str(e)}')
            return results

    def cleanup_old_data(self, model_name, retention_days=90):
        """
        Clean up old data safely.

        Args:
            model_name: str - Model to clean
            retention_days: int - Keep records newer than this

        Returns:
            dict: {deleted: int, kept: int}
        """
        from datetime import datetime, timedelta

        results = {'deleted': 0, 'kept': 0}

        try:
            Model = self.env[model_name]
            cutoff_date = datetime.now() - timedelta(days=retention_days)

            old_records = Model.search([
                ('create_date', '<', cutoff_date.isoformat())
            ])

            results['deleted'] = len(old_records)
            old_records.unlink()

            recent_records = Model.search([
                ('create_date', '>=', cutoff_date.isoformat())
            ])
            results['kept'] = len(recent_records)

            self.log_migration(
                'cleanup_completed',
                f'{model_name}: {results["deleted"]} deleted, {results["kept"]} kept'
            )
            return results

        except Exception as e:
            self.log_migration('cleanup_error', f'{model_name}: {str(e)}')
            return results

    def get_migration_summary(self):
        """Get summary of migration operations"""
        duration = (datetime.now() - self.migration_start).total_seconds() / 60

        return {
            'start_time': self.migration_start.isoformat(),
            'end_time': datetime.now().isoformat(),
            'duration_minutes': round(duration, 2),
            'total_operations': len(self.migration_log),
            'operations': self.migration_log
        }
