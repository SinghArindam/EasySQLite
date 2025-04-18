# easysqlite/db.py
"""
EasySQLite: A user-friendly Python wrapper for SQLite databases.
"""

import sqlite3
import os
import logging
import warnings
from typing import (List, Dict, Optional, Any, Union, Tuple, Generator)
from pathlib import Path

from .exceptions import (
    EasySQLiteError, DatabaseError, TableError, ColumnError, RowError, QueryError, JoinError
)

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EasySQLite")

# --- Constants ---
SUPPORTED_JOIN_TYPES = {'INNER', 'LEFT', 'CROSS'} # SQLite supports LEFT, INNER, CROSS natively
# RIGHT and FULL OUTER can sometimes be simulated but are not directly supported.

class EasySQLite:
    """
    A lightweight wrapper around Python's sqlite3 module to simplify common
    database operations.

    Provides an intuitive, high-level API using Python functions and data
    structures, abstracting away much of the SQL boilerplate.

    Attributes:
        db_path (str): Path to the SQLite database file.
        conn (Optional[sqlite3.Connection]): The SQLite connection object.
        cursor (Optional[sqlite3.Cursor]): The SQLite cursor object.
    """

    def __init__(self, db_path: Union[str, Path] = 'mydatabase.db'):
        """
        Initializes the EasySQLite instance and connects to the database.

        Creates the database file and necessary directories if they don't exist.

        Args:
            db_path (Union[str, Path]): The path to the SQLite database file.
                                        Defaults to 'mydatabase.db'.
        """
        self.db_path = str(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self._connect()

    def _connect(self):
        """Establishes the database connection."""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created directory: {db_dir}")

            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Use Row factory for dictionary-like access
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            logger.info(f"Successfully connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database {self.db_path}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to connect to {self.db_path}: {e}") from e

    def close(self):
        """Closes the database connection."""
        if self.conn:
            try:
                self.conn.commit() # Commit any pending changes before closing
                self.conn.close()
                logger.info(f"Database connection closed for: {self.db_path}")
                self.conn = None
                self.cursor = None
            except sqlite3.Error as e:
                logger.error(f"Error closing database connection {self.db_path}: {e}", exc_info=True)
                # Decide if we should raise an exception here or just log
                # raise DatabaseError(f"Failed to close connection cleanly: {e}") from e

    def __enter__(self):
        """Enters the runtime context related to this object."""
        if not self.conn or not self.cursor:
            self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exits the runtime context, handling commit/rollback and closing."""
        if self.conn:
            if exc_type:
                logger.warning(f"Exception occurred ({exc_type.__name__}), rolling back transaction.")
                try:
                    self.conn.rollback()
                except sqlite3.Error as e:
                     logger.error(f"Failed to rollback transaction: {e}", exc_info=True)
            else:
                try:
                    self.conn.commit()
                except sqlite3.Error as e:
                     logger.error(f"Failed to commit transaction: {e}", exc_info=True)
                     # Optionally re-raise or wrap in a custom exception
                     # raise DatabaseError(f"Commit failed: {e}") from e
            self.close()

    def _execute_sql(self, sql: str, params: Optional[Union[Tuple, Dict]] = None, operation_type: str = "query") -> Dict[str, Any]:
        """
        Internal helper method to execute SQL queries safely.

        Args:
            sql (str): The SQL query string.
            params (Optional[Union[Tuple, Dict]]): Parameters for the query.
            operation_type (str): Describes the type of operation for logging/error context.

        Returns:
            Dict[str, Any]: A dictionary containing results of the execution:
                {'success': bool, 'data': Optional[List[Dict]], 'rowcount': int,
                 'lastrowid': Optional[int], 'error': Optional[str]}
        """
        if not self.conn or not self.cursor:
            logger.error("Cannot execute SQL: Database connection is not active.")
            return {'success': False, 'data': None, 'rowcount': -1, 'lastrowid': None, 'error': "Database connection not active."}

        result = {
            'success': False,
            'data': None,
            'rowcount': -1,
            'lastrowid': None,
            'error': None
        }
        try:
            logger.debug(f"Executing SQL: {sql} with params: {params}")
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)

            result['rowcount'] = self.cursor.rowcount
            result['lastrowid'] = self.cursor.lastrowid

            # Check if the query was a SELECT or similar (returns data)
            # cursor.description is None for statements that don't return rows
            if self.cursor.description:
                 rows = self.cursor.fetchall()
                 # Convert sqlite3.Row objects to standard dictionaries
                 result['data'] = [dict(row) for row in rows]
            else:
                result['data'] = [] # No data expected for non-select

            result['success'] = True
            # No commit here; handled by context manager or explicit close()

        except sqlite3.Error as e:
            logger.error(f"SQL {operation_type} error: {e}\nQuery: {sql}\nParams: {params}", exc_info=True)
            result['error'] = str(e)
            # Rollback might be appropriate here if not using context manager exclusively,
            # but the PRD suggests context manager handles it.
            # self.conn.rollback() # Be cautious if adding explicit rollback here
        except Exception as e: # Catch broader exceptions
            logger.error(f"Unexpected error during SQL execution: {e}\nQuery: {sql}\nParams: {params}", exc_info=True)
            result['error'] = f"Unexpected error: {str(e)}"

        return result

    # --- 5.1 Database Management ---

    @staticmethod
    def list_databases(directory: str = '.') -> List[str]:
        """
        Lists SQLite database files (.db, .sqlite) in a given directory.

        Args:
            directory (str): The directory path to search in. Defaults to current directory.

        Returns:
            List[str]: A list of full paths to found database files.

        Raises:
            FileNotFoundError: If the specified directory does not exist.
        """
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")

        db_files = []
        try:
            for filename in os.listdir(directory):
                if filename.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                    full_path = os.path.join(directory, filename)
                    if os.path.isfile(full_path):
                        db_files.append(full_path)
        except OSError as e:
            logger.error(f"Error listing files in directory {directory}: {e}", exc_info=True)
            # Re-raise or handle as appropriate for the library's error strategy
            raise DatabaseError(f"Could not read directory {directory}: {e}") from e
        return db_files

    @staticmethod
    def delete_database(db_path: Union[str, Path], confirm: bool = True) -> bool:
        """
        Deletes the specified SQLite database file from the filesystem.

        Args:
            db_path (Union[str, Path]): The path to the database file to delete.
            confirm (bool): If True (default), prompt the user for confirmation
                            before deletion. If False, delete directly.

        Returns:
            bool: True if the file was successfully deleted, False otherwise.
        """
        db_path_str = str(db_path)
        if not os.path.exists(db_path_str):
            logger.warning(f"Database file not found, cannot delete: {db_path_str}")
            return False
        if not os.path.isfile(db_path_str):
             logger.warning(f"Path exists but is not a file, cannot delete: {db_path_str}")
             return False

        confirmation = 'y'
        if confirm:
            try:
                 confirmation = input(f"Are you sure you want to permanently delete '{db_path_str}'? (y/N): ").strip().lower()
            except EOFError: # Handle non-interactive environments gracefully
                 logger.warning("Cannot get confirmation in non-interactive mode. Deletion cancelled.")
                 confirmation = 'n'


        if confirmation == 'y':
            try:
                os.remove(db_path_str)
                logger.info(f"Successfully deleted database file: {db_path_str}")
                return True
            except OSError as e:
                logger.error(f"Error deleting database file {db_path_str}: {e}", exc_info=True)
                return False
            except Exception as e: # Catch broader exceptions
                logger.error(f"Unexpected error deleting database file {db_path_str}: {e}", exc_info=True)
                return False
        else:
            logger.info(f"Deletion cancelled for: {db_path_str}")
            return False

    # --- 5.2 Table Management ---

    def create_table(self, table_name: str, columns: Dict[str, str],
                     primary_key: Optional[Union[str, List[str]]] = None,
                     constraints: Optional[List[str]] = None,
                     if_not_exists: bool = True) -> bool:
        """
        Creates a table in the database.

        Args:
            table_name (str): The name of the table to create.
            columns (Dict[str, str]): A dictionary mapping column names to their
                                     SQLite data types (e.g., {'id': 'INTEGER', 'name': 'TEXT'}).
                                     Include constraints like NOT NULL here (e.g., 'INTEGER NOT NULL').
                                     For autoincrementing primary keys, use 'INTEGER PRIMARY KEY AUTOINCREMENT'.
            primary_key (Optional[Union[str, List[str]]]): Column name(s) for the primary key.
                                                         If using 'INTEGER PRIMARY KEY AUTOINCREMENT' in columns,
                                                         this can often be omitted or set to that column name.
                                                         Use a list for composite keys.
            constraints (Optional[List[str]]): A list of additional table-level constraints
                                              (e.g., ['UNIQUE (email)', 'CHECK (age > 0)']).
            if_not_exists (bool): If True (default), use 'CREATE TABLE IF NOT EXISTS'.

        Returns:
            bool: True if the table was created or already exists, False on error.

        Raises:
            TableError: If table name or column definitions are invalid.
            ValueError: If column dictionary is empty.
        """
        if not columns:
             raise ValueError("Columns dictionary cannot be empty.")
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'. Must be a valid identifier.")
        for col_name in columns.keys():
            if not col_name.isidentifier():
                raise TableError(f"Invalid column name: '{col_name}'. Must be a valid identifier.")


        cols_definitions = []
        has_explicit_pk_in_type = False
        for name, type_def in columns.items():
            cols_definitions.append(f'"{name}" {type_def}')
            if 'primary key' in type_def.lower():
                 has_explicit_pk_in_type = True


        sql = f"CREATE TABLE {'IF NOT EXISTS' if if_not_exists else ''} \"{table_name}\" ("
        sql += ", ".join(cols_definitions)

        pk_added = False
        if primary_key and not has_explicit_pk_in_type:
            if isinstance(primary_key, str):
                sql += f', PRIMARY KEY ("{primary_key}")'
                pk_added = True
            elif isinstance(primary_key, list) and primary_key:
                pk_cols = '", "'.join(primary_key)
                sql += f', PRIMARY KEY ("{pk_cols}")'
                pk_added = True

        if constraints:
            sql += ", " + ", ".join(constraints)

        sql += ");"

        result = self._execute_sql(sql, operation_type="create_table")
        if not result['success'] and 'already exists' not in (result['error'] or '').lower():
             raise TableError(f"Failed to create table '{table_name}': {result['error']}")
        # If 'already exists' error occurred but if_not_exists was True, it's not a failure.
        return result['success'] or (if_not_exists and 'already exists' in (result['error'] or '').lower())


    def list_tables(self) -> List[str]:
        """
        Retrieves a list of all table names in the database.

        Returns:
            List[str]: A list of table names. Returns empty list on error.
        """
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        result = self._execute_sql(sql, operation_type="list_tables")
        if result['success'] and result['data'] is not None:
            # Data is list of dicts like [{'name': 'table1'}, {'name': 'table2'}]
            return [row['name'] for row in result['data']]
        else:
            logger.error(f"Failed to list tables: {result['error']}")
            return []

    def describe_table(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Provides detailed information about each column in a table.

        Uses PRAGMA table_info.

        Args:
            table_name (str): The name of the table to describe.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each describing a column:
                                  {'cid': int, 'name': str, 'type': str, 'notnull': bool,
                                   'dflt_value': Any, 'pk': bool}.
                                   Returns empty list if table not found or on error.
        Raises:
            TableError: If the table does not exist or description fails.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name provided: '{table_name}'")

        # Check if table exists first to provide a better error message
        if table_name not in self.list_tables():
             raise TableError(f"Table '{table_name}' does not exist.")

        sql = f'PRAGMA table_info("{table_name}");'
        # PRAGMA might not work with standard parameterization, safe as table name is checked
        result = self._execute_sql(sql, operation_type="describe_table")

        if result['success'] and result['data'] is not None:
            # Convert PRAGMA result types for clarity
            description = []
            for col_info in result['data']:
                description.append({
                    'cid': col_info['cid'],
                    'name': col_info['name'],
                    'type': col_info['type'].upper(), # Standardize type case
                    'notnull': bool(col_info['notnull']), # Convert 0/1 to bool
                    'dflt_value': col_info['dflt_value'],
                    'pk': bool(col_info['pk']) # Convert 0/1 to bool
                })
            return description
        else:
             # This case should ideally be caught by the existence check above
             logger.error(f"Failed to describe table '{table_name}': {result['error']}")
             raise TableError(f"Could not describe table '{table_name}': {result['error']}")


    def rename_table(self, old_name: str, new_name: str) -> bool:
        """
        Renames an existing table.

        Args:
            old_name (str): The current name of the table.
            new_name (str): The desired new name for the table.

        Returns:
            bool: True on success, False otherwise.

        Raises:
            TableError: If names are invalid or the operation fails.
        """
        if not old_name or not old_name.isidentifier():
             raise TableError(f"Invalid old table name: '{old_name}'")
        if not new_name or not new_name.isidentifier():
             raise TableError(f"Invalid new table name: '{new_name}'")

        sql = f'ALTER TABLE "{old_name}" RENAME TO "{new_name}";'
        result = self._execute_sql(sql, operation_type="rename_table")
        if not result['success']:
             logger.error(f"Failed to rename table '{old_name}' to '{new_name}': {result['error']}")
             # Raise specific error if table doesn't exist?
             if "no such table" in (result['error'] or "").lower():
                 raise TableError(f"Table '{old_name}' does not exist.")
             raise TableError(f"Failed to rename table: {result['error']}")

        return result['success']

    def delete_table(self, table_name: str, force: bool = False) -> bool:
        """
        Deletes (drops) the specified table.

        Args:
            table_name (str): The name of the table to delete.
            force (bool): If False (default), prompts for confirmation.
                          If True, drops the table without prompting.

        Returns:
            bool: True on success, False otherwise (or if cancelled).

        Raises:
            TableError: If table name is invalid or operation fails.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")

        confirmation = 'y'
        if not force:
            try:
                 confirmation = input(f"Are you sure you want to permanently delete table '{table_name}'? (y/N): ").strip().lower()
            except EOFError:
                 logger.warning("Cannot get confirmation in non-interactive mode. Deletion cancelled.")
                 confirmation = 'n'

        if confirmation == 'y':
            sql = f'DROP TABLE IF EXISTS "{table_name}";'
            result = self._execute_sql(sql, operation_type="delete_table")
            if not result['success']:
                 logger.error(f"Failed to delete table '{table_name}': {result['error']}")
                 # Don't raise if IF EXISTS handled it, but log anyway if needed
                 if 'no such table' not in (result['error'] or '').lower():
                      raise TableError(f"Failed to delete table '{table_name}': {result['error']}")
                 else:
                     return True # Table didn't exist, which is success in the context of IF EXISTS
            logger.info(f"Table '{table_name}' deleted successfully.")
            return True
        else:
            logger.info(f"Deletion cancelled for table: {table_name}")
            return False

    # --- 5.3 Column Management ---

    def _get_sqlite_version(self) -> tuple:
        """Gets the runtime SQLite library version."""
        try:
            version_tuple = sqlite3.sqlite_version_info
            return version_tuple
        except Exception as e:
            logger.warning(f"Could not determine SQLite version: {e}")
            return (0, 0, 0) # Assume lowest compatibility if check fails


    def add_column(self, table_name: str, column_name: str, column_type: str,
                   default_value: Optional[Any] = None) -> bool:
        """
        Adds a new column to an existing table using ALTER TABLE ... ADD COLUMN.

        Args:
            table_name (str): Name of the table to modify.
            column_name (str): Name of the new column.
            column_type (str): SQLite data type for the new column (e.g., 'TEXT', 'INTEGER').
            default_value (Optional[Any]): Default value for the new column.
                                          Use None for no default. Strings will be quoted.

        Returns:
            bool: True on success, False otherwise.

        Raises:
            TableError: If table does not exist.
            ColumnError: If column name is invalid or operation fails.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not column_name or not column_name.isidentifier():
             raise ColumnError(f"Invalid column name: '{column_name}'")
        if table_name not in self.list_tables():
             raise TableError(f"Table '{table_name}' does not exist.")


        sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'

        params = []
        if default_value is not None:
            # Handle default values carefully - use parameter for the value if possible,
            # but ALTER TABLE syntax requires literals for DEFAULT. Need escaping.
            # Basic quoting for strings, numbers as is. Be cautious.
            # Parameterization doesn't work directly in the DEFAULT clause.
            if isinstance(default_value, str):
                 # Basic escape for single quotes within the string literal
                 escaped_value = default_value.replace("'", "''")
                 sql += f" DEFAULT '{escaped_value}'"
            elif isinstance(default_value, (int, float)):
                 sql += f" DEFAULT {default_value}"
            elif isinstance(default_value, bytes):
                 # SQLite expects BLOB literals in X'...' format
                 sql += f" DEFAULT X'{default_value.hex()}'"
            elif default_value is None: # Explicitly handle None -> NULL
                sql += " DEFAULT NULL"
            else:
                 # Fallback for other types (like bool maybe? converted to 0/1 by driver?)
                 # Or raise an error for unsupported default types.
                 logger.warning(f"Default value type {type(default_value)} might not be correctly handled in DEFAULT clause. Trying literal conversion.")
                 sql += f" DEFAULT {default_value}" # This might fail for complex types

        sql += ";"

        result = self._execute_sql(sql, params=None, operation_type="add_column") # No params needed here

        if not result['success']:
             logger.error(f"Failed to add column '{column_name}' to table '{table_name}': {result['error']}")
             raise ColumnError(f"Failed to add column '{column_name}': {result['error']}")
        return result['success']

    def rename_column(self, table_name: str, old_name: str, new_name: str) -> bool:
        """
        Renames an existing column using ALTER TABLE ... RENAME COLUMN.

        Note: Requires SQLite version 3.25.0 or higher.

        Args:
            table_name (str): The name of the table containing the column.
            old_name (str): The current name of the column.
            new_name (str): The desired new name for the column.

        Returns:
            bool: True on success, False otherwise.

        Raises:
            TableError: If table does not exist.
            ColumnError: If column names are invalid or operation fails (e.g., due to SQLite version).
            NotImplementedError: If SQLite version is too low.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not old_name or not old_name.isidentifier():
             raise ColumnError(f"Invalid old column name: '{old_name}'")
        if not new_name or not new_name.isidentifier():
             raise ColumnError(f"Invalid new column name: '{new_name}'")
        if table_name not in self.list_tables():
             raise TableError(f"Table '{table_name}' does not exist.")

        sqlite_version = self._get_sqlite_version()
        if sqlite_version < (3, 25, 0):
            msg = (f"RENAME COLUMN requires SQLite 3.25.0+ (found {sqlite3.sqlite_version}). "
                   "This operation cannot be performed safely with the current version.")
            logger.error(msg)
            raise NotImplementedError(msg)
            # Alternatively, could try the complex copy/recreate workaround here,
            # but that's significantly more complex and error-prone.

        sql = f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}";'
        result = self._execute_sql(sql, operation_type="rename_column")

        if not result['success']:
            logger.error(f"Failed to rename column '{old_name}' to '{new_name}' in table '{table_name}': {result['error']}")
            if "no such column" in (result['error'] or "").lower():
                raise ColumnError(f"Column '{old_name}' does not exist in table '{table_name}'.")
            raise ColumnError(f"Failed to rename column: {result['error']}")

        return result['success']

    def delete_column(self, table_name: str, column_name: str) -> bool:
        """
        Deletes (drops) an existing column using ALTER TABLE ... DROP COLUMN.

        Note: Requires SQLite version 3.35.0 or higher. This library does NOT
        implement the copy/recreate workaround for older versions due to complexity.

        Args:
            table_name (str): The name of the table containing the column.
            column_name (str): The name of the column to delete.

        Returns:
            bool: True on success, False otherwise.

        Raises:
            TableError: If table does not exist.
            ColumnError: If column name is invalid or operation fails (e.g., due to SQLite version).
            NotImplementedError: If SQLite version is too low.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not column_name or not column_name.isidentifier():
             raise ColumnError(f"Invalid column name: '{column_name}'")
        if table_name not in self.list_tables():
             raise TableError(f"Table '{table_name}' does not exist.")

        sqlite_version = self._get_sqlite_version()
        if sqlite_version < (3, 35, 0):
            msg = (f"DROP COLUMN requires SQLite 3.35.0+ (found {sqlite3.sqlite_version}). "
                   "This operation cannot be performed safely with the current version.")
            logger.error(msg)
            raise NotImplementedError(msg)

        sql = f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}";'
        result = self._execute_sql(sql, operation_type="delete_column")

        if not result['success']:
            logger.error(f"Failed to delete column '{column_name}' from table '{table_name}': {result['error']}")
            # Note: SQLite might give a generic "near 'DROP': syntax error" on older versions
            # even if the version check passed (e.g., if check failed somehow).
            if "no such column" in (result['error'] or "").lower():
                 raise ColumnError(f"Column '{column_name}' does not exist in table '{table_name}'.")
            raise ColumnError(f"Failed to delete column: {result['error']}")

        return result['success']

    # --- 5.4 Row Management ---

    def add_row(self, table_name: str, data: Dict[str, Any]) -> Optional[int]:
        """
        Inserts a single row into the specified table.

        Args:
            table_name (str): The name of the table.
            data (Dict[str, Any]): A dictionary mapping column names to values for the new row.

        Returns:
            Optional[int]: The rowid of the inserted row, or None on failure.

        Raises:
            TableError: If table name is invalid.
            RowError: If insertion fails (e.g., constraint violation, no such table/column).
            ValueError: If data dictionary is empty.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not data:
            raise ValueError("Data dictionary cannot be empty for add_row.")

        columns = list(data.keys())
        values = list(data.values())
        placeholders = ', '.join(['?'] * len(columns))
        cols_str = '", "'.join(columns)

        sql = f'INSERT INTO "{table_name}" ("{cols_str}") VALUES ({placeholders});'

        result = self._execute_sql(sql, tuple(values), operation_type="add_row")

        if result['success']:
            return result.get('lastrowid')
        else:
            logger.error(f"Failed to add row to table '{table_name}': {result['error']}")
            # Check for common errors
            err_lower = (result['error'] or "").lower()
            if "no such table" in err_lower:
                raise TableError(f"Table '{table_name}' does not exist.")
            elif "no such column" in err_lower:
                 # Extract column name if possible (difficult from generic error)
                 raise RowError(f"Insertion failed: {result['error']} (check column names)")
            elif "unique constraint" in err_lower:
                 raise RowError(f"Insertion failed due to UNIQUE constraint: {result['error']}")
            elif "not null constraint" in err_lower:
                 raise RowError(f"Insertion failed due to NOT NULL constraint: {result['error']}")
            else:
                 raise RowError(f"Failed to add row: {result['error']}")

    def add_rows(self, table_name: str, data_list: List[Dict[str, Any]]) -> int:
        """
        Inserts multiple rows into the table efficiently using executemany.

        Assumes all dictionaries in data_list have the same keys (columns).
        Uses the keys from the first dictionary to determine columns.

        Args:
            table_name (str): The name of the table.
            data_list (List[Dict[str, Any]]): A list of dictionaries, each representing a row.

        Returns:
            int: The number of rows successfully inserted (usually len(data_list) on success).
                 Returns 0 or less on failure.

        Raises:
            TableError: If table name is invalid.
            RowError: If insertion fails.
            ValueError: If data_list is empty or contains non-dict items or inconsistent keys.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not data_list:
            logger.warning("data_list is empty, no rows to add.")
            return 0
        if not isinstance(data_list[0], dict):
            raise ValueError("Items in data_list must be dictionaries.")

        # Use keys from the first item; assume consistency
        columns = list(data_list[0].keys())
        if not columns:
             raise ValueError("First data dictionary has no keys (columns).")

        cols_str = '", "'.join(columns)
        placeholders = ', '.join(['?'] * len(columns))
        sql = f'INSERT INTO "{table_name}" ("{cols_str}") VALUES ({placeholders});'

        # Convert list of dicts to list of tuples in the correct order
        try:
            values_list = [tuple(row[col] for col in columns) for row in data_list]
        except KeyError as e:
             raise ValueError(f"Inconsistent keys in data_list. Missing key: {e}")
        except TypeError:
             raise ValueError("Items in data_list must be dictionaries.")


        # Use a separate cursor for executemany as it behaves differently
        # especially regarding rowcount across different Python/sqlite versions.
        # Re-use self.cursor should be fine though.
        if not self.conn or not self.cursor:
             logger.error("Cannot execute SQL: Database connection is not active.")
             raise DatabaseError("Database connection not active.")

        inserted_count = 0
        try:
            logger.debug(f"Executing executemany SQL: {sql} with {len(values_list)} rows.")
            # Note: executemany's rowcount behaviour isn't always reliable across versions/drivers
            # for returning total rows inserted. We'll return len(data_list) on apparent success.
            self.cursor.executemany(sql, values_list)
            # Manually set success count if no exception occurred
            inserted_count = len(data_list) # Assume all inserted if no error
             # No commit here; handled by context manager or explicit close()
            logger.info(f"Attempted to add {len(data_list)} rows to '{table_name}'.")
            return inserted_count # Best guess on success
        except sqlite3.Error as e:
            logger.error(f"SQL executemany error: {e}\nQuery: {sql}", exc_info=True)
            # Rollback might be needed if not using context manager
            err_lower = str(e).lower()
            # Raise specific errors based on common issues
            if "no such table" in err_lower:
                raise TableError(f"Table '{table_name}' does not exist.")
            elif "no such column" in err_lower:
                 raise RowError(f"Insertion failed: {e} (check column names)")
            elif "unique constraint" in err_lower:
                 raise RowError(f"Insertion failed due to UNIQUE constraint: {e}")
            elif "not null constraint" in err_lower:
                 raise RowError(f"Insertion failed due to NOT NULL constraint: {e}")
            else:
                raise RowError(f"Failed to add rows using executemany: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during executemany: {e}", exc_info=True)
            raise RowError(f"Unexpected error adding rows: {e}")


    def _build_where_clause(self,
                           condition: Optional[Dict[str, Any]] = None,
                           condition_logic: str = 'AND',
                           operators: Optional[Dict[str, str]] = None
                           ) -> Tuple[str, List[Any]]:
        """
        Helper to build WHERE clause string and parameters safely.

        Args:
            condition (Optional[Dict[str, Any]]): Conditions {column: value}.
            condition_logic (str): 'AND' or 'OR'.
            operators (Optional[Dict[str, str]]): Operators per column {'col': '>='}. Defaults to '='.

        Returns:
            Tuple[str, List[Any]]: (where_clause_string, parameters_list)
                                   Example: ("WHERE name = ? AND age > ?", ['Alice', 30])
                                   Returns ("", []) if condition is empty or None.
        """
        if not condition:
            return "", []

        operators = operators or {}
        logic_separator = f" {condition_logic.upper()} "
        conditions = []
        params = []

        valid_operators = {'=', '!=', '<>', '<', '>', '<=', '>=', 'LIKE', 'NOT LIKE', 'IS', 'IS NOT', 'IN', 'NOT IN'}

        for col, val in condition.items():
             # Basic check for valid column names (more robust checks might be needed depending on source)
             # Ensure no SQL injection possibility here if col names come from unsafe sources!
             # PRD assumes they are developer-provided.
             if not col or not isinstance(col, str): # Simple check
                 raise ValueError(f"Invalid column name in condition: {col}")

             op = operators.get(col, '=').strip().upper()
             if op not in valid_operators:
                 raise ValueError(f"Unsupported operator '{op}' for column '{col}'. Supported: {valid_operators}")

             # Handle special cases like IS NULL, IS NOT NULL, IN, NOT IN
             if op in ('IS', 'IS NOT') and val is None:
                 conditions.append(f'"{col}" {op} NULL')
                 # No parameter needed for IS NULL / IS NOT NULL
             elif op in ('IN', 'NOT IN'):
                 if not isinstance(val, (list, tuple, set)) or not val:
                     raise ValueError(f"Value for {op} operator on column '{col}' must be a non-empty list, tuple, or set.")
                 placeholders = ', '.join(['?'] * len(val))
                 conditions.append(f'"{col}" {op} ({placeholders})')
                 params.extend(list(val))
             else:
                 # Standard case (e.g., =, >, LIKE)
                 conditions.append(f'"{col}" {op} ?')
                 params.append(val)


        if conditions:
            where_clause = "WHERE " + logic_separator.join(conditions)
            return where_clause, params
        else:
            return "", []


    def get_rows(self,
                 table_name: str,
                 columns: List[str] = ['*'],
                 condition: Optional[Dict[str, Any]] = None,
                 condition_logic: str = 'AND',
                 operators: Optional[Dict[str, str]] = None,
                 order_by: Optional[Union[str, List[str]]] = None,
                 limit: Optional[int] = None,
                 offset: Optional[int] = None
                 ) -> List[Dict[str, Any]]:
        """
        Retrieves rows from a table based on specified criteria.

        Args:
            table_name (str): The name of the table.
            columns (List[str]): List of column names to select. Defaults to ['*'].
                                Use 'table.column' format if needed (e.g., after joins).
            condition (Optional[Dict[str, Any]]): Dictionary for WHERE clause filters.
                                                  e.g., {'name': 'Alice', 'status': 1}.
            condition_logic (str): How to combine conditions ('AND' or 'OR'). Defaults to 'AND'.
            operators (Optional[Dict[str, str]]): Specify operators other than '=' for conditions.
                                                  e.g., {'age': '>', 'name': 'LIKE'}.
            order_by (Optional[Union[str, List[str]]]): Column name(s) for ordering.
                                                         e.g., 'name ASC', ['age DESC', 'name'].
                                                         Use 'table.column' format if needed.
            limit (Optional[int]): Maximum number of rows to return.
            offset (Optional[int]): Number of rows to skip.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each representing a row.
                                  Returns empty list if no matches or on error.

        Raises:
            TableError: If table name is invalid.
            QueryError: If query construction or execution fails.
            ValueError: If input parameters are invalid (e.g., bad operator, condition format).
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not columns:
             raise ValueError("Columns list cannot be empty.")

        # Validate columns - very basic check for potentially problematic chars; needs improvement for full safety
        safe_columns = []
        for col in columns:
             if col == '*':
                 safe_columns.append('*')
             # Allow table.column format, basic check for identifier parts
             elif '.' in col:
                 parts = col.split('.', 1)
                 if len(parts) == 2 and parts[0].isidentifier() and (parts[1].isidentifier() or parts[1] == '*'):
                      safe_columns.append(f'"{parts[0]}"."{parts[1]}"')
                 else:
                      raise ValueError(f"Invalid column format: '{col}'")
             elif col.isidentifier():
                 safe_columns.append(f'"{col}"')
             else:
                 raise ValueError(f"Invalid column name: '{col}'")

        select_cols = ', '.join(safe_columns)

        sql = f'SELECT {select_cols} FROM "{table_name}"'

        try:
            where_clause, params = self._build_where_clause(condition, condition_logic, operators)
            sql += f" {where_clause}"
        except ValueError as e:
             raise QueryError(f"Failed to build WHERE clause: {e}") from e


        if order_by:
            order_parts = []
            if isinstance(order_by, str):
                order_by_list = [order_by]
            elif isinstance(order_by, list):
                order_by_list = order_by
            else:
                raise ValueError("order_by must be a string or a list of strings.")

            for item in order_by_list:
                parts = item.strip().split()
                col_name = parts[0]
                direction = parts[1].upper() if len(parts) > 1 else 'ASC'

                # Validate column name (allow table.col) and direction
                safe_col_name = ""
                if '.' in col_name:
                    t_parts = col_name.split('.', 1)
                    if len(t_parts) == 2 and t_parts[0].isidentifier() and t_parts[1].isidentifier():
                        safe_col_name = f'"{t_parts[0]}"."{t_parts[1]}"'
                    else:
                         raise ValueError(f"Invalid ORDER BY column format: '{col_name}'")
                elif col_name.isidentifier():
                    safe_col_name = f'"{col_name}"'
                else:
                     raise ValueError(f"Invalid ORDER BY column name: '{col_name}'")

                if direction not in ('ASC', 'DESC'):
                    raise ValueError(f"Invalid ORDER BY direction: '{direction}'. Use 'ASC' or 'DESC'.")

                order_parts.append(f"{safe_col_name} {direction}")

            if order_parts:
                 sql += " ORDER BY " + ", ".join(order_parts)


        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                 raise ValueError("LIMIT must be a non-negative integer.")
            sql += " LIMIT ?"
            params.append(limit)

        if offset is not None:
            if limit is None: # Offset requires Limit in SQLite standard syntax
                 raise ValueError("OFFSET requires LIMIT to be set.")
            if not isinstance(offset, int) or offset < 0:
                 raise ValueError("OFFSET must be a non-negative integer.")
            sql += " OFFSET ?"
            params.append(offset)

        sql += ";"

        result = self._execute_sql(sql, tuple(params), operation_type="get_rows")

        if result['success'] and result['data'] is not None:
            return result['data']
        elif not result['success']:
            # Raise an error if execution failed
            err_lower = (result['error'] or "").lower()
            if "no such table" in err_lower:
                 raise TableError(f"Table '{table_name}' does not exist.")
            elif "no such column" in err_lower:
                 # Difficult to pinpoint which column without parsing SQL/error
                 raise QueryError(f"Query failed: {result['error']} (check column names in SELECT, WHERE, ORDER BY)")
            else:
                 raise QueryError(f"Failed to get rows: {result['error']}")
        else:
             # Success was True, but data was None (shouldn't happen with fetchall) or empty
             return [] # Return empty list for no results found


    def update_rows(self,
                    table_name: str,
                    data: Dict[str, Any],
                    condition: Dict[str, Any],
                    condition_logic: str = 'AND',
                    operators: Optional[Dict[str, str]] = None
                    ) -> int:
        """
        Updates rows in a table that match the given condition.

        Args:
            table_name (str): The name of the table.
            data (Dict[str, Any]): Dictionary of columns and their new values to set.
            condition (Dict[str, Any]): Dictionary for the WHERE clause to select rows for update.
                                       Cannot be empty for safety.
            condition_logic (str): How to combine conditions ('AND' or 'OR'). Defaults to 'AND'.
            operators (Optional[Dict[str, str]]): Operators for the WHERE clause conditions.

        Returns:
            int: The number of rows affected by the update. Returns -1 on error.

        Raises:
            TableError: If table name is invalid.
            RowError: If update fails.
            ValueError: If data or condition dictionaries are empty or invalid.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not data:
            raise ValueError("Data dictionary for SET clause cannot be empty.")
        if not condition:
            raise ValueError("Condition dictionary cannot be empty for update_rows (safety measure).")

        set_clauses = []
        set_params = []
        for col, val in data.items():
             if not col or not col.isidentifier():
                 raise ValueError(f"Invalid column name in data for SET: '{col}'")
             set_clauses.append(f'"{col}" = ?')
             set_params.append(val)

        set_clause_str = ", ".join(set_clauses)

        sql = f'UPDATE "{table_name}" SET {set_clause_str}'

        try:
            where_clause, where_params = self._build_where_clause(condition, condition_logic, operators)
            if not where_clause: # Double check, should be prevented by condition check above
                 raise ValueError("Cannot perform UPDATE without a WHERE clause (condition was empty).")
            sql += f" {where_clause}"
        except ValueError as e:
             raise RowError(f"Failed to build WHERE clause for UPDATE: {e}") from e

        sql += ";"
        params = tuple(set_params + where_params)

        result = self._execute_sql(sql, params, operation_type="update_rows")

        if result['success']:
            return result.get('rowcount', 0) # rowcount might be 0 if no rows matched
        else:
            err_lower = (result['error'] or "").lower()
            if "no such table" in err_lower:
                 raise TableError(f"Table '{table_name}' does not exist.")
            elif "no such column" in err_lower:
                 raise RowError(f"Update failed: {result['error']} (check column names in SET or WHERE)")
            elif "unique constraint" in err_lower:
                 raise RowError(f"Update failed due to UNIQUE constraint: {result['error']}")
            elif "not null constraint" in err_lower:
                 raise RowError(f"Update failed due to NOT NULL constraint: {result['error']}")
            else:
                raise RowError(f"Failed to update rows: {result['error']}")


    def delete_rows(self,
                    table_name: str,
                    condition: Dict[str, Any],
                    condition_logic: str = 'AND',
                    operators: Optional[Dict[str, str]] = None,
                    force_delete_all: bool = False
                   ) -> int:
        """
        Deletes rows from a table that match the given condition.

        Args:
            table_name (str): The name of the table.
            condition (Dict[str, Any]): Dictionary for the WHERE clause to select rows for deletion.
                                       Required unless force_delete_all is True.
            condition_logic (str): How to combine conditions ('AND' or 'OR'). Defaults to 'AND'.
            operators (Optional[Dict[str, str]]): Operators for the WHERE clause conditions.
            force_delete_all (bool): If True, allows deleting all rows by providing an empty
                                     or None condition. USE WITH EXTREME CAUTION. Defaults to False.

        Returns:
            int: The number of rows affected (deleted). Returns -1 on error.

        Raises:
            TableError: If table name is invalid.
            RowError: If deletion fails.
            ValueError: If condition is empty and force_delete_all is False, or if parameters invalid.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")
        if not condition and not force_delete_all:
            raise ValueError("Condition dictionary cannot be empty for delete_rows unless "
                             "force_delete_all=True is set (safety measure).")

        sql = f'DELETE FROM "{table_name}"'

        params = []
        if condition:
            try:
                where_clause, where_params = self._build_where_clause(condition, condition_logic, operators)
                if where_clause:
                    sql += f" {where_clause}"
                    params = where_params
            except ValueError as e:
                 raise RowError(f"Failed to build WHERE clause for DELETE: {e}") from e
        elif not force_delete_all:
             # This case should be caught by the initial check, but as a safeguard:
             raise ValueError("Condition is missing and force_delete_all is False.")
        # If force_delete_all is True and condition is empty, proceed without WHERE clause


        sql += ";"
        params_tuple = tuple(params) if params else None # Pass None if no params

        result = self._execute_sql(sql, params_tuple, operation_type="delete_rows")

        if result['success']:
            return result.get('rowcount', 0) # rowcount might be 0 if no rows matched
        else:
            err_lower = (result['error'] or "").lower()
            if "no such table" in err_lower:
                 raise TableError(f"Table '{table_name}' does not exist.")
            elif "no such column" in err_lower: # Should only happen if condition referenced non-existent col
                 raise RowError(f"Delete failed: {result['error']} (check column names in condition)")
            else:
                raise RowError(f"Failed to delete rows: {result['error']}")

    def count_rows(self,
                   table_name: str,
                   condition: Optional[Dict[str, Any]] = None,
                   condition_logic: str = 'AND',
                   operators: Optional[Dict[str, str]] = None
                  ) -> int:
        """
        Counts the number of rows in a table, optionally matching a condition.

        Args:
            table_name (str): The name of the table.
            condition (Optional[Dict[str, Any]]): Dictionary for WHERE clause filters.
            condition_logic (str): How to combine conditions ('AND' or 'OR'). Defaults to 'AND'.
            operators (Optional[Dict[str, str]]): Operators for the WHERE clause conditions.

        Returns:
            int: The number of rows matching the criteria. Returns -1 on error.

        Raises:
            TableError: If table name is invalid.
            QueryError: If counting fails.
            ValueError: If condition parameters are invalid.
        """
        if not table_name or not table_name.isidentifier():
             raise TableError(f"Invalid table name: '{table_name}'")

        sql = f'SELECT COUNT(*) as count FROM "{table_name}"'

        params = []
        if condition:
            try:
                where_clause, where_params = self._build_where_clause(condition, condition_logic, operators)
                if where_clause:
                    sql += f" {where_clause}"
                    params = where_params
            except ValueError as e:
                 raise QueryError(f"Failed to build WHERE clause for COUNT: {e}") from e

        sql += ";"
        params_tuple = tuple(params) if params else None

        result = self._execute_sql(sql, params_tuple, operation_type="count_rows")

        if result['success'] and result['data'] and isinstance(result['data'], list) and len(result['data']) == 1:
            # Data should be [{'count': N}]
             return result['data'][0].get('count', 0)
        elif result['success']: # Query ran but maybe returned unexpected data format?
             logger.warning(f"Count query for '{table_name}' succeeded but returned unexpected data format: {result['data']}")
             return 0 # Or maybe raise an error? Returning 0 might be safer.
        else:
             # Raise specific errors
             err_lower = (result['error'] or "").lower()
             if "no such table" in err_lower:
                 raise TableError(f"Table '{table_name}' does not exist.")
             elif "no such column" in err_lower:
                 raise QueryError(f"Count failed: {result['error']} (check column names in condition)")
             else:
                 raise QueryError(f"Failed to count rows: {result['error']}")


    # --- 5.5 Joins ---

    def join_rows(self,
                  base_table: str,
                  joins: List[Dict[str, str]],
                  columns: List[str] = ['*'],
                  condition: Optional[Dict[str, Any]] = None,
                  condition_logic: str = 'AND',
                  operators: Optional[Dict[str, str]] = None,
                  order_by: Optional[Union[str, List[str]]] = None,
                  limit: Optional[int] = None,
                  offset: Optional[int] = None
                  ) -> List[Dict[str, Any]]:
        """
        Performs JOIN operations between tables and retrieves rows.

        Args:
            base_table (str): The main table in the FROM clause.
            joins (List[Dict[str, str]]): A list of dictionaries, each defining a JOIN.
                Required keys per dict:
                - 'type' (str): The JOIN type ('INNER', 'LEFT', 'CROSS').
                                Note: SQLite handles RIGHT/FULL OUTER poorly or not at all.
                - 'target_table' (str): The table to join with.
                - 'on' (str): The JOIN condition string (e.g., 'users.id = orders.user_id').
                              IMPORTANT: Use fully qualified column names (table.column)
                              in the 'on' condition string. The library does NOT parse
                              or automatically qualify these names.
            columns (List[str]): List of columns to select. Use 'table.column' format
                                 to avoid ambiguity. Defaults to ['*'].
            condition (Optional[Dict[str, Any]]): WHERE clause filters. Use 'table.column'.
            condition_logic (str): 'AND' or 'OR' for WHERE clause.
            operators (Optional[Dict[str, str]]): Operators for WHERE clause. Use 'table.column'.
            order_by (Optional[Union[str, List[str]]]): Ordering columns. Use 'table.column'.
            limit (Optional[int]): Max rows.
            offset (Optional[int]): Rows to skip.

        Returns:
            List[Dict[str, Any]]: List of dictionaries representing the joined rows.

        Raises:
            TableError: If base_table name is invalid.
            JoinError: If join parameters are invalid or the operation fails.
            QueryError: If query construction or execution fails.
            ValueError: If input parameters like columns, condition, order_by are invalid.
        """
        if not base_table or not base_table.isidentifier():
             raise TableError(f"Invalid base table name: '{base_table}'")
        if not joins:
             raise ValueError("Joins list cannot be empty for join_rows operation.")

        # --- Column Selection ---
        # Reuse validation logic from get_rows, adapted for potential table prefixes
        safe_columns = []
        if not columns: raise ValueError("Columns list cannot be empty.")
        for col in columns:
             if col == '*':
                 safe_columns.append('*')
             elif '.' in col: # Expect table.column format mostly
                 parts = col.split('.', 1)
                 if len(parts) == 2 and parts[0].isidentifier() and (parts[1].isidentifier() or parts[1] == '*'):
                      safe_columns.append(f'"{parts[0]}"."{parts[1]}"')
                 else:
                      raise ValueError(f"Invalid column format: '{col}' - use 'table.column' or '*'")
             elif col.isidentifier():
                 # Allow unqualified names but warn user about ambiguity risk
                 warnings.warn(f"Using unqualified column name '{col}' in JOIN. Use 'table.column' to avoid ambiguity.", UserWarning)
                 safe_columns.append(f'"{col}"')
             else:
                 raise ValueError(f"Invalid column name: '{col}'")
        select_cols = ', '.join(safe_columns)

        sql = f'SELECT {select_cols} FROM "{base_table}"'

        # --- Build Joins ---
        join_parts = []
        for join_info in joins:
            if not isinstance(join_info, dict):
                 raise JoinError("Each item in 'joins' list must be a dictionary.")
            join_type = join_info.get('type', '').upper()
            target_table = join_info.get('target_table')
            on_condition = join_info.get('on')

            if join_type not in SUPPORTED_JOIN_TYPES:
                 raise JoinError(f"Unsupported JOIN type: '{join_type}'. Supported: {SUPPORTED_JOIN_TYPES}")
            if not target_table or not target_table.isidentifier():
                 raise JoinError(f"Invalid target table name in join: '{target_table}'")
            if not on_condition or not isinstance(on_condition, str):
                 raise JoinError(f"Missing or invalid 'on' condition string for join with '{target_table}'")

            # Important: The 'on_condition' is used directly. It's the user's responsibility
            # to ensure it's syntactically correct and uses qualified names.
            # Avoid embedding parameters here for safety.
            join_parts.append(f'{join_type} JOIN "{target_table}" ON {on_condition}')

        sql += " " + " ".join(join_parts)

        # --- Build Where Clause ---
        # The _build_where_clause helper needs column names prefixed appropriately by the caller
        # in the `condition` and `operators` dicts.
        try:
            where_clause, params = self._build_where_clause(condition, condition_logic, operators)
            if where_clause:
                sql += f" {where_clause}"
        except ValueError as e:
             raise QueryError(f"Failed to build WHERE clause for JOIN: {e}") from e

        # --- Build Order By ---
        # Reuse validation logic from get_rows, expecting table.column format
        if order_by:
            order_parts = []
            if isinstance(order_by, str):
                order_by_list = [order_by]
            elif isinstance(order_by, list):
                order_by_list = order_by
            else:
                raise ValueError("order_by must be a string or a list of strings.")

            for item in order_by_list:
                 parts = item.strip().split()
                 col_spec = parts[0] # e.g., "users.name"
                 direction = parts[1].upper() if len(parts) > 1 else 'ASC'

                 safe_col_name = ""
                 if '.' in col_spec:
                     t_parts = col_spec.split('.', 1)
                     if len(t_parts) == 2 and t_parts[0].isidentifier() and t_parts[1].isidentifier():
                         safe_col_name = f'"{t_parts[0]}"."{t_parts[1]}"'
                     else:
                         raise ValueError(f"Invalid ORDER BY column format: '{col_spec}' - use 'table.column'")
                 elif col_spec.isidentifier():
                     # Discourage unqualified names in joins, but allow if explicitly identifier
                     warnings.warn(f"Using unqualified column name '{col_spec}' in JOIN ORDER BY. Use 'table.column'.", UserWarning)
                     safe_col_name = f'"{col_spec}"'
                 else:
                     raise ValueError(f"Invalid ORDER BY column spec: '{col_spec}'")


                 if direction not in ('ASC', 'DESC'):
                     raise ValueError(f"Invalid ORDER BY direction: '{direction}'. Use 'ASC' or 'DESC'.")

                 order_parts.append(f"{safe_col_name} {direction}")

            if order_parts:
                 sql += " ORDER BY " + ", ".join(order_parts)


        # --- Limit and Offset ---
        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                 raise ValueError("LIMIT must be a non-negative integer.")
            sql += " LIMIT ?"
            params.append(limit)

        if offset is not None:
            if limit is None:
                 raise ValueError("OFFSET requires LIMIT to be set.")
            if not isinstance(offset, int) or offset < 0:
                 raise ValueError("OFFSET must be a non-negative integer.")
            sql += " OFFSET ?"
            params.append(offset)

        sql += ";"

        # --- Execute ---
        result = self._execute_sql(sql, tuple(params), operation_type="join_rows")

        if result['success'] and result['data'] is not None:
            return result['data']
        elif not result['success']:
            # Raise appropriate error based on message
            err_lower = (result['error'] or "").lower()
            if "no such table" in err_lower:
                 # Could be base table or one of the join targets
                 raise TableError(f"Join failed: {result['error']} (check table names)")
            elif "no such column" in err_lower:
                 raise QueryError(f"Join failed: {result['error']} (check column names in SELECT, ON, WHERE, ORDER BY)")
            elif "ambiguous column name" in err_lower:
                 raise QueryError(f"Join failed: {result['error']} (use 'table.column' format)")
            else:
                 raise JoinError(f"Failed to execute JOIN query: {result['error']}")
        else:
             return [] # Success but no data


    # --- 5.6 Custom Query ---

    def execute_query(self, sql: str, params: Optional[Union[Tuple, Dict]] = None) -> Dict[str, Any]:
        """
        Executes a raw SQL query provided by the user.

        Uses parameterization if `params` are provided, which is STRONGLY recommended
        to prevent SQL injection vulnerabilities if the query involves external input.

        WARNING: If you build the `sql` string using external/user input WITHOUT using
        `params`, your application may be vulnerable to SQL injection. Parameterization
        only protects the *values* passed via `params`, not identifiers (table/column names)
        or SQL keywords embedded directly in the `sql` string.

        Args:
            sql (str): The raw SQL query string to execute.
            params (Optional[Union[Tuple, Dict]]): A tuple or dictionary of parameters
                to bind to placeholders ('?' or ':name') in the SQL query.

        Returns:
            Dict[str, Any]: A dictionary containing the execution result:
                - success (bool): True if execution was successful, False otherwise.
                - data (Optional[List[Dict]]): List of dictionaries for SELECT results. None otherwise.
                - rowcount (int): Number of rows affected by INSERT/UPDATE/DELETE (-1 if not applicable/error).
                - lastrowid (Optional[int]): The rowid of the last inserted row (if applicable).
                - error (Optional[str]): Error message if success is False.
        """
        # Use the internal _execute_sql helper which handles execution, errors, and data fetching
        logger.warning("Executing custom query. Ensure SQL is safe, especially if constructed from external input.")
        if params:
            logger.info("Using parameterization for custom query.")
        else:
             # Check for common DML keywords to warn if params seems missing but might be needed
             sql_upper = sql.upper()
             if any(keyword in sql_upper for keyword in ["INSERT ", "UPDATE ", "DELETE ", "VALUES(", "SET ", "WHERE "]):
                 logger.warning("Custom query appears to modify data or filter without parameters. Ensure this is intentional and safe.")


        result = self._execute_sql(sql, params, operation_type="custom_query")

        # If the execution failed within _execute_sql, result['success'] will be False
        # and result['error'] will be populated.
        # If a custom exception is preferred for execute_query failures:
        # if not result['success']:
        #     raise QueryError(f"Custom query execution failed: {result['error']}")

        return result

# Example Usage (can be placed in a separate file or under if __name__ == "__main__":)
if __name__ == '__main__':

    DB_FILE = 'test_easysqlite_example.db'

    # Clean up previous run
    if os.path.exists(DB_FILE):
        EasySQLite.delete_database(DB_FILE, confirm=False)

    print("--- Basic Operations ---")
    # Using context manager for automatic connection handling
    try:
        with EasySQLite(DB_FILE) as db:
            # Create tables
            print("Creating tables...")
            db.create_table('users', {'id': 'INTEGER PRIMARY KEY AUTOINCREMENT', 'name': 'TEXT NOT NULL', 'email': 'TEXT UNIQUE'})
            db.create_table('posts', {
                'post_id': 'INTEGER PRIMARY KEY',
                'user_id': 'INTEGER',
                'title': 'TEXT',
                'content': 'TEXT'
            }, constraints=['FOREIGN KEY (user_id) REFERENCES users(id)'])
            print("Tables created:", db.list_tables())

            # Add single row
            print("Adding single user...")
            user1_id = db.add_row('users', {'name': 'Alice', 'email': 'alice@example.com'})
            print(f"Added user Alice with id: {user1_id}")

            # Add multiple rows
            print("Adding multiple users...")
            users_to_add = [
                {'name': 'Bob', 'email': 'bob@example.com'},
                {'name': 'Charlie', 'email': 'charlie@example.com'}
            ]
            added_count = db.add_rows('users', users_to_add)
            print(f"Added {added_count} more users.")

            # Get rows
            print("Getting all users:")
            all_users = db.get_rows('users')
            for user in all_users:
                print(dict(user)) # sqlite3.Row is dict-like

            # Get rows with condition
            print("Getting user Bob:")
            bob = db.get_rows('users', condition={'name': 'Bob'})
            print(bob)

            # Get rows with condition using operator
            print("Getting users with ID > 1:")
            users_gt1 = db.get_rows('users', condition={'id': 1}, operators={'id': '>'})
            print(users_gt1)

            # Count rows
            print("Counting all users:")
            user_count = db.count_rows('users')
            print(f"Total users: {user_count}")

            # Update rows
            print("Updating Bob's email...")
            updated_count = db.update_rows('users', {'email': 'bob_updated@example.com'}, condition={'name': 'Bob'})
            print(f"Updated {updated_count} row(s).")
            print("Bob after update:", db.get_rows('users', condition={'name': 'Bob'}))

            # Add posts
            print("Adding posts...")
            db.add_rows('posts', [
                {'post_id': 101, 'user_id': user1_id, 'title': 'Alice Post 1', 'content': 'Content...'},
                {'post_id': 102, 'user_id': user1_id, 'title': 'Alice Post 2', 'content': 'More...'},
                {'post_id': 201, 'user_id': user1_id + 1, 'title': 'Bob Post 1', 'content': 'Stuff...'} # Assumes Bob is ID 2
            ])

            # Join rows
            print("Joining users and posts (LEFT JOIN):")
            join_def = [{
                'type': 'LEFT',
                'target_table': 'posts',
                'on': 'users.id = posts.user_id' # Crucial: Qualified names
            }]
            # Select specific columns using table prefix
            joined_data = db.join_rows(
                base_table='users',
                joins=join_def,
                columns=['users.name', 'users.email', 'posts.title'],
                condition={'users.id': user1_id}, # Filter by user ID
                 operators={'users.id': '='}
            )
            print("Alice's posts:")
            for row in joined_data:
                 print(dict(row))


            # Describe table
            print("Describing 'users' table:")
            print(db.describe_table('users'))

            # Add column
            print("Adding 'status' column to users...")
            db.add_column('users', 'status', 'TEXT', default_value='active')
            print("Users table description after adding column:")
            print(db.describe_table('users'))
            print("Users data after adding column:")
            print(db.get_rows('users'))


             # Execute custom query (parameterized SELECT)
            print("Executing custom SELECT query:")
            custom_result = db.execute_query("SELECT name FROM users WHERE email LIKE ?", ('%@example.com',))
            if custom_result['success']:
                 print("Custom query results:", custom_result['data'])
            else:
                 print("Custom query failed:", custom_result['error'])

            # Delete rows
            print("Deleting Charlie...")
            deleted_count = db.delete_rows('users', condition={'name': 'Charlie'})
            print(f"Deleted {deleted_count} row(s).")
            print("Remaining users:", db.count_rows('users'))

            # Rename table (if needed)
            # print("Renaming users to customers...")
            # db.rename_table('users', 'customers')
            # print("Tables after rename:", db.list_tables())
            # db.rename_table('customers', 'users') # Rename back

            # Delete table (with confirmation simulated via force=True here)
            # print("Deleting posts table...")
            # db.delete_table('posts', force=True)
            # print("Tables after delete:", db.list_tables())


    except EasySQLiteError as e:
         print(f"\nAn EasySQLite error occurred: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

    finally:
         # Optional: Final cleanup outside the example usage
         print("\n--- Listing existing DB files ---")
         print(EasySQLite.list_databases('.'))
         # pass
         # Uncomment to delete the DB after the example runs
         # if os.path.exists(DB_FILE):
         #     print(f"Cleaning up {DB_FILE}...")
         #     EasySQLite.delete_database(DB_FILE, confirm=False)