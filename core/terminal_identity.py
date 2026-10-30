"""Identidad persistente por instalación física del POS."""
import uuid


def terminal_id():
    from database_manager import DatabaseManager
    db=DatabaseManager()
    value=db.get_config_value("POS_TERMINAL_ID")
    if not value:
        value="caja-"+uuid.uuid4().hex
        db.set_config("POS_TERMINAL_ID",value)
    return value
