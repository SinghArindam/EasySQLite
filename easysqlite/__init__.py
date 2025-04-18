# easysqlite/__init__.py
"""
EasySQLite Library Package.

Provides the EasySQLite class for simplified SQLite database interactions.
"""

__version__ = "0.1.2" # Version based on PRD

from .db import EasySQLite
from .exceptions import (
    EasySQLiteError, DatabaseError, TableError, ColumnError, RowError, QueryError, JoinError
)

# Define what gets imported with 'from easysqlite import *'
__all__ = [
    'EasySQLite',
    'EasySQLiteError',
    'DatabaseError',
    'TableError',
    'ColumnError',
    'RowError',
    'QueryError',
    'JoinError',
]