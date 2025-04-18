# tests/test_easysqlite.py
"""
Unit tests for the EasySQLite library.
"""

import unittest
import os
import sqlite3
from unittest.mock import patch
from pathlib import Path

# Assume the project structure allows this import
# If running directly, you might need to adjust sys.path
# Or run using `python -m unittest discover tests` from the project root
from easysqlite import (
    EasySQLite,
    EasySQLiteError,
    DatabaseError,
    TableError,
    ColumnError,
    RowError,
    QueryError,
    JoinError
)

class TestEasySQLite(unittest.TestCase):
    """Test suite for the EasySQLite class."""

    DB_FILE = 'test_easysqlite_suite.db'
    OTHER_DB_FILE = 'other_test_db.db'
    TEST_DIR = 'test_db_dir'

    def setUp(self):
        """Set up for test methods."""
        # Ensure clean slate before each test
        self._cleanup_files()
        # Create test directory if needed
        os.makedirs(self.TEST_DIR, exist_ok=True)
        # Create the main DB instance for most tests
        self.db = EasySQLite(self.DB_FILE)

    def tearDown(self):
        """Tear down after test methods."""
        if self.db and self.db.conn:
            self.db.close()
        self._cleanup_files()
        if os.path.exists(self.TEST_DIR):
            os.rmdir(self.TEST_DIR) # Remove dir only if empty

    def _cleanup_files(self):
        """Helper to remove test DB files and dirs."""
        files_to_remove = [self.DB_FILE, self.OTHER_DB_FILE]
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
        # Clean up potential files in test dir
        if os.path.exists(self.TEST_DIR):
             for item in os.listdir(self.TEST_DIR):
                 item_path = os.path.join(self.TEST_DIR, item)
                 if os.path.isfile(item_path):
                     os.remove(item_path)


    # --- 5.1 Database Management Tests ---

    def test_init_creates_file(self):
        """Test if __init__ creates the database file."""
        self.assertTrue(os.path.exists(self.DB_FILE))
        self.assertIsNotNone(self.db.conn)
        self.assertIsNotNone(self.db.cursor)

    def test_init_creates_directory(self):
        """Test if __init__ creates the directory if it doesn't exist."""
        nested_db_path = os.path.join(self.TEST_DIR, 'nested', 'test.db')
        if os.path.exists(nested_db_path): os.remove(nested_db_path)
        nested_dir = os.path.dirname(nested_db_path)
        if os.path.exists(nested_dir): os.rmdir(nested_dir)

        db_nested = EasySQLite(nested_db_path)
        self.assertTrue(os.path.exists(nested_dir))
        self.assertTrue(os.path.exists(nested_db_path))
        db_nested.close()
        os.remove(nested_db_path)
        os.rmdir(nested_dir)


    def test_close_connection(self):
        """Test closing the connection."""
        self.db.close()
        self.assertIsNone(self.db.conn)
        self.assertIsNone(self.db.cursor)
        # Try an operation after close - should fail or reconnect if designed to
        with self.assertRaises(EasySQLiteError): # Expecting an error or custom exception subclass
             self.db.list_tables() # Operation requires connection

    def test_context_manager_commit(self):
        """Test context manager commits changes."""
        with EasySQLite(self.DB_FILE) as db_ctx:
            db_ctx.create_table('temp', {'id': 'INTEGER'})
            db_ctx.add_row('temp', {'id': 1})

        # Reconnect to check if data was committed
        with EasySQLite(self.DB_FILE) as db_check:
            rows = db_check.get_rows('temp')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], 1)

    def test_context_manager_rollback(self):
        """Test context manager rolls back on exception."""
        with EasySQLite(self.DB_FILE) as db_setup:
            db_setup.create_table('temp', {'id': 'INTEGER UNIQUE'})
            db_setup.add_row('temp', {'id': 1})

        try:
            with EasySQLite(self.DB_FILE) as db_ctx:
                db_ctx.add_row('temp', {'id': 2}) # Should succeed
                # This should fail due to UNIQUE constraint and trigger rollback
                db_ctx.add_row('temp', {'id': 1})
        except RowError: # Catch the expected exception
            pass
        except Exception as e:
             self.fail(f"Unexpected exception during rollback test: {e}")


        # Reconnect to check if id=2 was rolled back
        with EasySQLite(self.DB_FILE) as db_check:
            rows = db_check.get_rows('temp')
            self.assertEqual(len(rows), 1) # Only the initial id=1 should exist
            self.assertEqual(rows[0]['id'], 1)

    def test_list_databases(self):
        """Test listing database files."""
        # Create some dummy files
        Path(os.path.join(self.TEST_DIR, 'test1.db')).touch()
        Path(os.path.join(self.TEST_DIR, 'test2.sqlite')).touch()
        Path(os.path.join(self.TEST_DIR, 'test3.sqlite3')).touch()
        Path(os.path.join(self.TEST_DIR, 'not_a_db.txt')).touch()
        os.makedirs(os.path.join(self.TEST_DIR, 'subdir'), exist_ok=True)
        Path(os.path.join(self.TEST_DIR, 'subdir', 'nested.db')).touch()

        dbs = EasySQLite.list_databases(self.TEST_DIR)
        dbs_relative = [os.path.basename(p) for p in dbs]

        self.assertIn('test1.db', dbs_relative)
        self.assertIn('test2.sqlite', dbs_relative)
        self.assertIn('test3.sqlite3', dbs_relative)
        self.assertNotIn('not_a_db.txt', dbs_relative)
        self.assertNotIn('nested.db', dbs_relative) # Should not be recursive
        self.assertEqual(len(dbs), 3)

    def test_list_databases_not_found(self):
        """Test listing databases in a non-existent directory."""
        with self.assertRaises(FileNotFoundError):
            EasySQLite.list_databases('non_existent_directory')

    def test_delete_database_force(self):
        """Test deleting a database file with force=True."""
        # Create a dummy DB file
        other_db = EasySQLite(self.OTHER_DB_FILE)
        other_db.close()
        self.assertTrue(os.path.exists(self.OTHER_DB_FILE))

        # Delete without confirmation
        result = EasySQLite.delete_database(self.OTHER_DB_FILE, confirm=False)
        self.assertTrue(result)
        self.assertFalse(os.path.exists(self.OTHER_DB_FILE))

    @patch('builtins.input', return_value='y')
    def test_delete_database_confirm_yes(self, mock_input):
        """Test deleting a database file with confirmation 'y'."""
        other_db = EasySQLite(self.OTHER_DB_FILE)
        other_db.close()
        self.assertTrue(os.path.exists(self.OTHER_DB_FILE))

        result = EasySQLite.delete_database(self.OTHER_DB_FILE, confirm=True)
        self.assertTrue(result)
        self.assertFalse(os.path.exists(self.OTHER_DB_FILE))
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='n')
    def test_delete_database_confirm_no(self, mock_input):
        """Test cancelling database deletion with confirmation 'n'."""
        other_db = EasySQLite(self.OTHER_DB_FILE)
        other_db.close()
        self.assertTrue(os.path.exists(self.OTHER_DB_FILE))

        result = EasySQLite.delete_database(self.OTHER_DB_FILE, confirm=True)
        self.assertFalse(result)
        self.assertTrue(os.path.exists(self.OTHER_DB_FILE))
        mock_input.assert_called_once()

    def test_delete_database_not_exists(self):
        """Test deleting a non-existent database file."""
        self.assertFalse(os.path.exists(self.OTHER_DB_FILE))
        result = EasySQLite.delete_database(self.OTHER_DB_FILE, confirm=False)
        self.assertFalse(result)


    # --- 5.2 Table Management Tests ---

    def test_create_table_simple(self):
        """Test basic table creation."""
        result = self.db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
        self.assertTrue(result)
        self.assertIn('users', self.db.list_tables())

    def test_create_table_with_pk_constraint(self):
        """Test table creation with primary key and constraints."""
        result = self.db.create_table(
            'products',
            {'sku': 'TEXT', 'price': 'REAL NOT NULL'},
            primary_key='sku',
            constraints=['CHECK (price > 0)']
        )
        self.assertTrue(result)
        desc = self.db.describe_table('products')
        sku_col = next((col for col in desc if col['name'] == 'sku'), None)
        price_col = next((col for col in desc if col['name'] == 'price'), None)
        self.assertTrue(sku_col['pk'])
        self.assertTrue(price_col['notnull'])
        # Cannot easily verify CHECK constraint via PRAGMA

    def test_create_table_if_not_exists(self):
        """Test CREATE TABLE IF NOT EXISTS behavior."""
        self.assertTrue(self.db.create_table('users', {'id': 'INTEGER'}, if_not_exists=True))
        # Try creating again with IF NOT EXISTS (should succeed, return True)
        self.assertTrue(self.db.create_table('users', {'id': 'INTEGER'}, if_not_exists=True))
        # Try creating again *without* IF NOT EXISTS (should fail, raise TableError)
        with self.assertRaises(TableError):
             self.db.create_table('users', {'id': 'INTEGER'}, if_not_exists=False)

    def test_create_table_invalid_name(self):
        """Test creating a table with an invalid name."""
        with self.assertRaises(TableError):
            self.db.create_table('invalid-table-name', {'id': 'INTEGER'})
        with self.assertRaises(TableError):
            self.db.create_table('users', {'invalid-col-name': 'TEXT'})

    def test_list_tables(self):
        """Test listing tables."""
        self.assertEqual(self.db.list_tables(), [])
        self.db.create_table('table1', {'colA': 'TEXT'})
        self.assertEqual(self.db.list_tables(), ['table1'])
        self.db.create_table('table2', {'colB': 'INTEGER'})
        tables = self.db.list_tables()
        self.assertIn('table1', tables)
        self.assertIn('table2', tables)
        self.assertEqual(len(tables), 2)

    def test_describe_table(self):
        """Test describing a table."""
        self.db.create_table('items', {
            'item_id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'name': 'TEXT NOT NULL',
            'value': 'REAL DEFAULT 0.0'
        })
        desc = self.db.describe_table('items')
        self.assertEqual(len(desc), 3)

        id_col = desc[0]
        name_col = desc[1]
        value_col = desc[2]

        self.assertEqual(id_col['name'], 'item_id')
        self.assertEqual(id_col['type'], 'INTEGER')
        self.assertTrue(id_col['pk'])
        self.assertFalse(id_col['notnull']) # PK can be null before insert for AUTOINCREMENT

        self.assertEqual(name_col['name'], 'name')
        self.assertEqual(name_col['type'], 'TEXT')
        self.assertFalse(name_col['pk'])
        self.assertTrue(name_col['notnull'])

        self.assertEqual(value_col['name'], 'value')
        self.assertEqual(value_col['type'], 'REAL')
        self.assertFalse(value_col['pk'])
        self.assertFalse(value_col['notnull'])
        self.assertEqual(value_col['dflt_value'], '0.0')

    def test_describe_table_not_exists(self):
        """Test describing a non-existent table."""
        with self.assertRaises(TableError):
            self.db.describe_table('non_existent_table')

    def test_rename_table(self):
        """Test renaming a table."""
        self.db.create_table('old_table', {'col': 'TEXT'})
        self.assertTrue(self.db.rename_table('old_table', 'new_table'))
        tables = self.db.list_tables()
        self.assertIn('new_table', tables)
        self.assertNotIn('old_table', tables)

    def test_rename_table_not_exists(self):
        """Test renaming a non-existent table."""
        with self.assertRaises(TableError):
            self.db.rename_table('non_existent_table', 'new_name')

    def test_delete_table_force(self):
        """Test deleting a table with force=True."""
        self.db.create_table('temp_table', {'col': 'TEXT'})
        self.assertIn('temp_table', self.db.list_tables())
        self.assertTrue(self.db.delete_table('temp_table', force=True))
        self.assertNotIn('temp_table', self.db.list_tables())

    @patch('builtins.input', return_value='y')
    def test_delete_table_confirm_yes(self, mock_input):
        """Test deleting a table with confirmation 'y'."""
        self.db.create_table('temp_table', {'col': 'TEXT'})
        self.assertTrue(self.db.delete_table('temp_table', force=False))
        self.assertNotIn('temp_table', self.db.list_tables())
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='n')
    def test_delete_table_confirm_no(self, mock_input):
        """Test cancelling table deletion."""
        self.db.create_table('temp_table', {'col': 'TEXT'})
        self.assertFalse(self.db.delete_table('temp_table', force=False))
        self.assertIn('temp_table', self.db.list_tables())
        mock_input.assert_called_once()

    def test_delete_table_not_exists(self):
        """Test deleting a non-existent table (should succeed with IF EXISTS)."""
        # DROP TABLE IF EXISTS should not raise an error
        self.assertTrue(self.db.delete_table('non_existent_table', force=True))


    # --- 5.3 Column Management Tests ---
    # Helper to check SQLite version for feature availability
    def _sqlite_version_ge(self, major, minor, patch):
        return sqlite3.sqlite_version_info >= (major, minor, patch)

    def test_add_column(self):
        """Test adding a column."""
        self.db.create_table('users', {'id': 'INTEGER'})
        self.assertTrue(self.db.add_column('users', 'email', 'TEXT', default_value='N/A'))
        desc = self.db.describe_table('users')
        email_col = next((col for col in desc if col['name'] == 'email'), None)
        self.assertIsNotNone(email_col)
        self.assertEqual(email_col['type'], 'TEXT')
        self.assertEqual(email_col['dflt_value'], "'N/A'") # Note: default values are stored as strings

    def test_add_column_numeric_default(self):
        """Test adding a column with numeric default."""
        self.db.create_table('users', {'id': 'INTEGER'})
        self.assertTrue(self.db.add_column('users', 'score', 'INTEGER', default_value=0))
        desc = self.db.describe_table('users')
        score_col = next((col for col in desc if col['name'] == 'score'), None)
        self.assertIsNotNone(score_col)
        self.assertEqual(score_col['type'], 'INTEGER')
        self.assertEqual(score_col['dflt_value'], '0')

    def test_add_column_to_nonexistent_table(self):
        """Test adding a column to a non-existent table."""
        with self.assertRaises(TableError):
             self.db.add_column('non_existent', 'new_col', 'TEXT')

    def test_rename_column(self):
        """Test renaming a column (if supported)."""
        if not self._sqlite_version_ge(3, 25, 0):
            self.skipTest("SQLite version < 3.25.0 does not support RENAME COLUMN.")

        self.db.create_table('users', {'id': 'INTEGER', 'mail': 'TEXT'})
        self.assertTrue(self.db.rename_column('users', 'mail', 'email'))
        desc = self.db.describe_table('users')
        col_names = [col['name'] for col in desc]
        self.assertIn('email', col_names)
        self.assertNotIn('mail', col_names)

    def test_rename_column_unsupported(self):
        """Test renaming a column when unsupported."""
        if self._sqlite_version_ge(3, 25, 0):
            self.skipTest("SQLite version >= 3.25.0 supports RENAME COLUMN.")

        self.db.create_table('users', {'id': 'INTEGER', 'mail': 'TEXT'})
        with self.assertRaises(NotImplementedError):
            self.db.rename_column('users', 'mail', 'email')

    def test_rename_nonexistent_column(self):
        """Test renaming a non-existent column."""
        if not self._sqlite_version_ge(3, 25, 0):
             self.skipTest("Skipping rename non-existent test on unsupported SQLite version.")

        self.db.create_table('users', {'id': 'INTEGER'})
        with self.assertRaises(ColumnError): # Or potentially specific subclass from db
            self.db.rename_column('users', 'nonexistent', 'new_name')

    def test_delete_column(self):
        """Test deleting a column (if supported)."""
        if not self._sqlite_version_ge(3, 35, 0):
            self.skipTest("SQLite version < 3.35.0 does not support DROP COLUMN.")

        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'temp': 'BLOB'})
        self.assertTrue(self.db.delete_column('users', 'temp'))
        desc = self.db.describe_table('users')
        col_names = [col['name'] for col in desc]
        self.assertNotIn('temp', col_names)
        self.assertEqual(len(col_names), 2)

    def test_delete_column_unsupported(self):
        """Test deleting a column when unsupported."""
        if self._sqlite_version_ge(3, 35, 0):
            self.skipTest("SQLite version >= 3.35.0 supports DROP COLUMN.")

        self.db.create_table('users', {'id': 'INTEGER', 'temp': 'BLOB'})
        with self.assertRaises(NotImplementedError):
            self.db.delete_column('users', 'temp')

    def test_delete_nonexistent_column(self):
        """Test deleting a non-existent column."""
        if not self._sqlite_version_ge(3, 35, 0):
            self.skipTest("Skipping delete non-existent test on unsupported SQLite version.")

        self.db.create_table('users', {'id': 'INTEGER'})
        with self.assertRaises(ColumnError): # Or potentially specific subclass from db
            self.db.delete_column('users', 'nonexistent')


    # --- 5.4 Row Management Tests ---

    def test_add_row(self):
        """Test adding a single row."""
        self.db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
        rowid = self.db.add_row('users', {'name': 'Alice'})
        self.assertIsInstance(rowid, int)
        self.assertGreater(rowid, 0)

        rows = self.db.get_rows('users')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Alice')
        self.assertEqual(rows[0]['id'], rowid)

    def test_add_row_violates_constraint(self):
        """Test adding a row that violates a UNIQUE constraint."""
        self.db.create_table('users', {'id': 'INTEGER', 'email': 'TEXT UNIQUE'})
        self.db.add_row('users', {'id': 1, 'email': 'test@example.com'})
        with self.assertRaises(RowError): # Specific exception might differ
            self.db.add_row('users', {'id': 2, 'email': 'test@example.com'})

    def test_add_rows(self):
        """Test adding multiple rows."""
        self.db.create_table('products', {'sku': 'TEXT', 'price': 'REAL'})
        data = [
            {'sku': 'A001', 'price': 10.99},
            {'sku': 'B002', 'price': 5.50},
        ]
        count = self.db.add_rows('products', data)
        self.assertEqual(count, 2)
        self.assertEqual(self.db.count_rows('products'), 2)

    def test_add_rows_empty_list(self):
        """Test adding an empty list of rows."""
        self.db.create_table('products', {'sku': 'TEXT'})
        count = self.db.add_rows('products', [])
        self.assertEqual(count, 0)

    def test_add_rows_inconsistent_keys(self):
        """Test adding rows with inconsistent keys."""
        self.db.create_table('products', {'sku': 'TEXT', 'price': 'REAL'})
        data = [
            {'sku': 'A001', 'price': 10.99},
            {'sku': 'B002'}, # Missing price
        ]
        with self.assertRaises(ValueError): # Expecting ValueError from implementation
            self.db.add_rows('products', data)

    def test_get_rows_all(self):
        """Test getting all rows."""
        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
        self.db.add_rows('users', [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
        rows = self.db.get_rows('users')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['name'], 'Alice')
        self.assertEqual(rows[1]['name'], 'Bob')

    def test_get_rows_specific_columns(self):
        """Test getting specific columns."""
        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'email': 'TEXT'})
        self.db.add_row('users', {'id': 1, 'name': 'Alice', 'email': 'a@ex.com'})
        rows = self.db.get_rows('users', columns=['id', 'name'])
        self.assertEqual(len(rows), 1)
        self.assertIn('id', rows[0])
        self.assertIn('name', rows[0])
        self.assertNotIn('email', rows[0])

    def test_get_rows_condition_simple(self):
        """Test getting rows with a simple condition."""
        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
        self.db.add_rows('users', [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
        rows = self.db.get_rows('users', condition={'name': 'Bob'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 2)

    def test_get_rows_condition_operators(self):
        """Test getting rows with different operators."""
        self.db.create_table('users', {'id': 'INTEGER', 'score': 'INTEGER', 'status': 'TEXT'})
        self.db.add_rows('users', [
            {'id': 1, 'score': 100, 'status': 'active'},
            {'id': 2, 'score': 150, 'status': 'active'},
            {'id': 3, 'score': 50, 'status': 'inactive'},
            {'id': 4, 'score': 150, 'status': None}
        ])
        # Greater than
        rows_gt = self.db.get_rows('users', condition={'score': 100}, operators={'score': '>'})
        self.assertEqual(len(rows_gt), 2)
        ids_gt = {r['id'] for r in rows_gt}
        self.assertEqual(ids_gt, {2, 4})
        # LIKE
        rows_like = self.db.get_rows('users', condition={'status': 'act%'}, operators={'status': 'LIKE'})
        self.assertEqual(len(rows_like), 2)
        # IS NULL
        rows_null = self.db.get_rows('users', condition={'status': None}, operators={'status': 'IS'})
        self.assertEqual(len(rows_null), 1)
        self.assertEqual(rows_null[0]['id'], 4)
        # IN
        rows_in = self.db.get_rows('users', condition={'id': [1, 3, 5]}, operators={'id': 'IN'})
        self.assertEqual(len(rows_in), 2)
        ids_in = {r['id'] for r in rows_in}
        self.assertEqual(ids_in, {1, 3})

    def test_get_rows_condition_logic_or(self):
        """Test getting rows with OR logic."""
        self.db.create_table('users', {'id': 'INTEGER', 'score': 'INTEGER', 'status': 'TEXT'})
        self.db.add_rows('users', [
            {'id': 1, 'score': 100, 'status': 'active'},
            {'id': 2, 'score': 50, 'status': 'inactive'},
            {'id': 3, 'score': 100, 'status': 'inactive'},
        ])
        rows = self.db.get_rows('users', condition={'score': 100, 'status': 'inactive'}, condition_logic='OR')
        self.assertEqual(len(rows), 3) # All rows match one or the other

    def test_get_rows_order_by(self):
        """Test ordering results."""
        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
        self.db.add_rows('users', [{'id': 2, 'name': 'Bob'}, {'id': 1, 'name': 'Alice'}, {'id': 3, 'name': 'Charlie'}])
        rows_asc = self.db.get_rows('users', order_by='name ASC')
        self.assertEqual([r['name'] for r in rows_asc], ['Alice', 'Bob', 'Charlie'])
        rows_desc = self.db.get_rows('users', order_by=['id DESC'])
        self.assertEqual([r['id'] for r in rows_desc], [3, 2, 1])

    def test_get_rows_limit_offset(self):
        """Test limit and offset."""
        self.db.create_table('items', {'num': 'INTEGER'})
        self.db.add_rows('items', [{'num': i} for i in range(1, 11)]) # 1 to 10
        rows = self.db.get_rows('items', order_by='num', limit=3, offset=5)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['num'] for r in rows], [6, 7, 8])

    def test_get_rows_offset_without_limit(self):
        """Test using offset without limit raises error."""
        self.db.create_table('items', {'num': 'INTEGER'})
        with self.assertRaises(ValueError):
            self.db.get_rows('items', offset=5)

    def test_update_rows(self):
        """Test updating rows."""
        self.db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'status': 'TEXT'})
        self.db.add_rows('users', [
            {'id': 1, 'name': 'Alice', 'status': 'pending'},
            {'id': 2, 'name': 'Bob', 'status': 'pending'},
            {'id': 3, 'name': 'Charlie', 'status': 'active'}
        ])
        affected = self.db.update_rows('users', {'status': 'approved'}, condition={'status': 'pending'})
        self.assertEqual(affected, 2)
        rows = self.db.get_rows('users', condition={'status': 'approved'})
        self.assertEqual(len(rows), 2)
        ids = {r['id'] for r in rows}
        self.assertEqual(ids, {1, 2})

    def test_update_rows_no_match(self):
        """Test updating rows when condition matches none."""
        self.db.create_table('users', {'id': 'INTEGER', 'status': 'TEXT'})
        self.db.add_row('users', {'id': 1, 'status': 'active'})
        affected = self.db.update_rows('users', {'status': 'inactive'}, condition={'id': 99})
        self.assertEqual(affected, 0)

    def test_update_rows_empty_data_or_condition(self):
        """Test update_rows with empty data or condition."""
        self.db.create_table('users', {'id': 'INTEGER'})
        with self.assertRaises(ValueError):
            self.db.update_rows('users', {}, condition={'id': 1})
        with self.assertRaises(ValueError):
            self.db.update_rows('users', {'id': 2}, condition={})

    def test_delete_rows(self):
        """Test deleting rows."""
        self.db.create_table('items', {'id': 'INTEGER', 'category': 'TEXT'})
        self.db.add_rows('items', [
            {'id': 1, 'category': 'A'}, {'id': 2, 'category': 'B'},
            {'id': 3, 'category': 'A'}, {'id': 4, 'category': 'C'}
        ])
        affected = self.db.delete_rows('items', condition={'category': 'A'})
        self.assertEqual(affected, 2)
        self.assertEqual(self.db.count_rows('items'), 2)
        remaining = self.db.get_rows('items')
        cats = {r['category'] for r in remaining}
        self.assertEqual(cats, {'B', 'C'})

    def test_delete_rows_no_match(self):
        """Test deleting rows when condition matches none."""
        self.db.create_table('items', {'id': 'INTEGER'})
        self.db.add_row('items', {'id': 1})
        affected = self.db.delete_rows('items', condition={'id': 99})
        self.assertEqual(affected, 0)
        self.assertEqual(self.db.count_rows('items'), 1)

    def test_delete_rows_requires_condition_or_force(self):
        """Test delete_rows safety measure (requires condition or force)."""
        self.db.create_table('items', {'id': 'INTEGER'})
        self.db.add_row('items', {'id': 1})
        # Should fail without condition and force=False
        with self.assertRaises(ValueError):
            self.db.delete_rows('items', condition={})
        with self.assertRaises(ValueError):
             self.db.delete_rows('items', condition=None)

    def test_delete_rows_force_delete_all(self):
        """Test deleting all rows with force_delete_all=True."""
        self.db.create_table('items', {'id': 'INTEGER'})
        self.db.add_rows('items', [{'id': 1}, {'id': 2}])
        affected = self.db.delete_rows('items', condition={}, force_delete_all=True)
        self.assertEqual(affected, 2)
        self.assertEqual(self.db.count_rows('items'), 0)

    def test_count_rows(self):
        """Test counting rows."""
        self.db.create_table('log', {'level': 'TEXT'})
        self.assertEqual(self.db.count_rows('log'), 0)
        self.db.add_rows('log', [{'level': 'INFO'}, {'level': 'WARN'}, {'level': 'INFO'}])
        self.assertEqual(self.db.count_rows('log'), 3)
        self.assertEqual(self.db.count_rows('log', condition={'level': 'INFO'}), 2)
        self.assertEqual(self.db.count_rows('log', condition={'level': 'ERROR'}), 0)

    # --- 5.5 Joins Tests ---

    def test_join_rows_left(self):
        """Test LEFT JOIN."""
        self.db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
        self.db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
        uid1 = self.db.add_row('users', {'name': 'Alice'})
        uid2 = self.db.add_row('users', {'name': 'Bob'}) # Bob has no posts
        self.db.add_row('posts', {'user_id': uid1, 'title': 'Alice Post 1'})

        joins = [{'type': 'LEFT', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
        results = self.db.join_rows(
            base_table='users',
            joins=joins,
            columns=['users.name', 'posts.title'],
            order_by='users.name'
        )

        self.assertEqual(len(results), 2)
        # Alice has a post
        self.assertEqual(results[0]['name'], 'Alice')
        self.assertEqual(results[0]['title'], 'Alice Post 1')
        # Bob has no post, title should be None
        self.assertEqual(results[1]['name'], 'Bob')
        self.assertIsNone(results[1]['title'])

    def test_join_rows_inner(self):
        """Test INNER JOIN."""
        self.db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
        self.db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
        uid1 = self.db.add_row('users', {'name': 'Alice'})
        uid2 = self.db.add_row('users', {'name': 'Bob'}) # Bob has no posts
        self.db.add_row('posts', {'user_id': uid1, 'title': 'Alice Post 1'})

        joins = [{'type': 'INNER', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
        results = self.db.join_rows(
            base_table='users',
            joins=joins,
            columns=['users.name', 'posts.title']
        )

        self.assertEqual(len(results), 1) # Only Alice should match
        self.assertEqual(results[0]['name'], 'Alice')
        self.assertEqual(results[0]['title'], 'Alice Post 1')

    def test_join_rows_with_condition(self):
        """Test JOIN with a WHERE condition."""
        self.db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
        self.db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
        uid1 = self.db.add_row('users', {'name': 'Alice'})
        uid2 = self.db.add_row('users', {'name': 'Bob'})
        self.db.add_row('posts', {'user_id': uid1, 'title': 'Post A'})
        self.db.add_row('posts', {'user_id': uid2, 'title': 'Post B'})

        joins = [{'type': 'INNER', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
        results = self.db.join_rows(
            base_table='users',
            joins=joins,
            columns=['users.name', 'posts.title'],
            condition={'users.name': 'Bob'} # Filter condition using table prefix
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Bob')
        self.assertEqual(results[0]['title'], 'Post B')

    def test_join_rows_invalid_type(self):
        """Test JOIN with an invalid join type."""
        self.db.create_table('users', {'id': 'INTEGER'})
        self.db.create_table('posts', {'post_id': 'INTEGER'})
        joins = [{'type': 'INVALID', 'target_table': 'posts', 'on': '1=1'}]
        with self.assertRaises(JoinError):
             self.db.join_rows('users', joins)

    # --- 5.6 Custom Query Tests ---

    def test_execute_query_select(self):
        """Test executing a custom SELECT query."""
        self.db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
        self.db.add_rows('data', [{'key': 'A', 'value': 10}, {'key': 'B', 'value': 20}])
        result = self.db.execute_query("SELECT value FROM data WHERE key = ? ORDER BY value", ('B',))
        self.assertTrue(result['success'])
        self.assertEqual(len(result['data']), 1)
        self.assertEqual(result['data'][0]['value'], 20)
        self.assertEqual(result['rowcount'], -1) # Rowcount often -1 for SELECT
        self.assertIsNone(result['lastrowid'])
        self.assertIsNone(result['error'])

    def test_execute_query_insert(self):
        """Test executing a custom INSERT query."""
        self.db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
        result = self.db.execute_query("INSERT INTO data (key, value) VALUES (?, ?)", ('C', 30))
        self.assertTrue(result['success'])
        self.assertIsNone(result['data']) # No data for INSERT
        self.assertEqual(result['rowcount'], 1)
        self.assertIsInstance(result['lastrowid'], int)
        self.assertIsNone(result['error'])
        # Verify insert
        rows = self.db.get_rows('data', condition={'key': 'C'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['value'], 30)

    def test_execute_query_update(self):
        """Test executing a custom UPDATE query."""
        self.db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
        self.db.add_row('data', {'key': 'D', 'value': 40})
        result = self.db.execute_query("UPDATE data SET value = ? WHERE key = ?", (45, 'D'))
        self.assertTrue(result['success'])
        self.assertIsNone(result['data'])
        self.assertEqual(result['rowcount'], 1)
        self.assertIsNone(result['lastrowid'])
        self.assertIsNone(result['error'])
        # Verify update
        rows = self.db.get_rows('data', condition={'key': 'D'})
        self.assertEqual(rows[0]['value'], 45)

    def test_execute_query_delete(self):
        """Test executing a custom DELETE query."""
        self.db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
        self.db.add_row('data', {'key': 'E', 'value': 50})
        result = self.db.execute_query("DELETE FROM data WHERE key = ?", ('E',))
        self.assertTrue(result['success'])
        self.assertIsNone(result['data'])
        self.assertEqual(result['rowcount'], 1)
        self.assertIsNone(result['lastrowid'])
        self.assertIsNone(result['error'])
        # Verify delete
        self.assertEqual(self.db.count_rows('data'), 0)

    def test_execute_query_invalid_sql(self):
        """Test executing invalid SQL."""
        result = self.db.execute_query("SELECT * FROM non_existent_table")
        self.assertFalse(result['success'])
        self.assertIsNone(result['data'])
        self.assertIn('no such table', result['error'].lower()) # Check for common error message

        result_syntax = self.db.execute_query("SELEC * FROM data")
        self.assertFalse(result_syntax['success'])
        self.assertIsNotNone(result_syntax['error'])
        self.assertIn('syntax error', result_syntax['error'].lower())


# Allows running the tests directly from the script
if __name__ == '__main__':
    unittest.main()
