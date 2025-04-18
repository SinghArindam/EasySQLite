# easysqlite/exceptions.py
"""Custom exceptions for the EasySQLite library."""

class EasySQLiteError(Exception):
    """Base exception class for EasySQLite errors."""
    pass

class DatabaseError(EasySQLiteError):
    """Exception related to database file operations."""
    pass

class TableError(EasySQLiteError):
    """Exception related to table operations."""
    pass

class ColumnError(EasySQLiteError):
    """Exception related to column operations."""
    pass

class RowError(EasySQLiteError):
    """Exception related to row operations."""
    pass

class QueryError(EasySQLiteError):
    """Exception related to custom query execution."""
    pass

class JoinError(EasySQLiteError):
    """Exception related to JOIN operations."""
    pass