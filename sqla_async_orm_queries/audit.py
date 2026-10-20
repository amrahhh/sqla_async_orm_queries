"""Opt-in audit logging.

Importing this module registers the ``audit_logs`` table. Then call
``YourModel.attach_listeners()`` for each model you want audited.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String

from .models import Model


class AuditLog(Model):
	__tablename__ = "audit_logs"
	id = Column(Integer, primary_key=True)
	table_name = Column(String)
	operation = Column(String)
	timestamp = Column(DateTime, default=lambda: datetime.now(tz=UTC))
	data = Column(JSON)
