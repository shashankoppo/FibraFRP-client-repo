# -*- coding: utf-8 -*-
import logging


_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    """Adopt existing AI records before this module loads its XML data.

    Existing databases originally created these records from
    ``elsx_whatsapp_marketing``. Creating an additional XML ID keeps the same
    row and primary key while allowing the AI core data files to take over.
    """
    env.cr.execute(
        """
        INSERT INTO ir_model_data
            (module, name, model, res_id, noupdate, create_date, write_date)
        SELECT
            'elsx_ai_core', legacy.name, legacy.model, legacy.res_id,
            legacy.noupdate, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
        FROM ir_model_data AS legacy
        WHERE legacy.module = 'elsx_whatsapp_marketing'
          AND (
              legacy.model LIKE 'elsx.ai.%%'
              OR legacy.name LIKE 'model_elsx_ai_%%'
              OR legacy.name LIKE 'field_elsx_ai_%%'
              OR legacy.name LIKE 'selection_elsx_ai_%%'
              OR legacy.name LIKE 'constraint_elsx_ai_%%'
              OR legacy.name LIKE 'access_elsx_ai_%%'
              OR legacy.name LIKE 'elsx_ai_provider_%%'
              OR legacy.name LIKE 'elsx_ai_prompt_%%'
          )
        ON CONFLICT (module, name) DO UPDATE
        SET model = EXCLUDED.model,
            res_id = EXCLUDED.res_id,
            write_date = now() AT TIME ZONE 'UTC'
        """
    )
    _logger.info('Adopted legacy ELSX AI XML IDs without copying AI records.')
