# tests/test_easysqlite.py
"""
Pytest test suite for the EasySQLite library.
"""

import pytest
import os
import sqlite3
from pathlib import Path

# Assume easysqlite is installed or available in the Python path
# Run using `pytest` command from the project root directory
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

# --- Helper Functions ---

def sqlite_version_ge(major, minor, patch):
    """Checks if the runtime SQLite version is >= the specified version."""
    return sqlite3.sqlite_version_info >= (major, minor, patch)

# --- Constants ---
# Using pytest's tmp_path fixture mostly removes the need for predefined file names,
# but we might need one for static method tests involving specific paths if not using tmp_path.
OTHER_DB_FILE = 'other_test_db_pytest.db'

# --- Fixtures ---

@pytest.fixture
def db_path(tmp_path):
    """Provides a Path object for the test database file in a temporary directory."""
    return tmp_path / "test_easysqlite.db"

@pytest.fixture
def other_db_path(tmp_path):
    """Provides a Path object for a secondary test database file."""
    return tmp_path / OTHER_DB_FILE

@pytest.fixture(scope="function")
def db(db_path):
    """
    Provides an EasySQLite instance connected to a clean database file for each test function.
    Handles connection closing automatically.
    """
    # Ensure clean state by default as tmp_path gives a unique dir per test
    db_instance = EasySQLite(db_path)
    yield db_instance
    # Teardown: Close the connection. File deletion is handled by tmp_path.
    db_instance.close()

@pytest.fixture
def test_dir(tmp_path):
    """Provides a temporary directory path (as string) for directory-based tests."""
    d = tmp_path / "db_dir_for_listing"
    d.mkdir()
    return str(d)


# --- 5.1 Database Management Tests ---

def test_init_creates_file(db_path):
    """Test if __init__ creates the database file."""
    assert not db_path.exists() # Should not exist before creation
    db_instance = EasySQLite(db_path)
    assert db_path.exists()
    assert db_instance.conn is not None
    assert db_instance.cursor is not None
    db_instance.close()

def test_init_creates_directory(tmp_path):
    """Test if __init__ creates the directory if it doesn't exist."""
    nested_dir = tmp_path / "nested_dir"
    nested_db_path = nested_dir / "test.db"

    assert not nested_dir.exists()
    db_nested = EasySQLite(nested_db_path)
    assert nested_dir.exists()
    assert nested_db_path.exists()
    db_nested.close()

def test_close_connection(db):
    """Test closing the connection."""
    assert db.conn is not None
    db.close()
    assert db.conn is None
    assert db.cursor is None
    # Try an operation after close - should fail
    with pytest.raises(EasySQLiteError): # Expecting base error or specific subclass
         db.list_tables() # Operation requires connection

def test_context_manager_commit(db_path):
    """Test context manager commits changes."""
    with EasySQLite(db_path) as db_ctx:
        db_ctx.create_table('temp', {'id': 'INTEGER'})
        db_ctx.add_row('temp', {'id': 1})

    # Reconnect to check if data was committed
    with EasySQLite(db_path) as db_check:
        rows = db_check.get_rows('temp')
        assert len(rows) == 1
        assert rows[0]['id'] == 1

def test_context_manager_rollback(db_path):
    """Test context manager rolls back on exception."""
    with EasySQLite(db_path) as db_setup:
        db_setup.create_table('temp', {'id': 'INTEGER UNIQUE'})
        db_setup.add_row('temp', {'id': 1}) # Initial data

    with pytest.raises(RowError): # Expect RowError due to UNIQUE constraint
        with EasySQLite(db_path) as db_ctx:
            db_ctx.add_row('temp', {'id': 2}) # Should succeed initially
            # This should fail due to UNIQUE constraint and trigger rollback
            db_ctx.add_row('temp', {'id': 1})

    # Reconnect to check if id=2 was rolled back
    with EasySQLite(db_path) as db_check:
        rows = db_check.get_rows('temp')
        assert len(rows) == 1 # Only the initial id=1 should exist
        assert rows[0]['id'] == 1

def test_list_databases(test_dir):
    """Test listing database files in a directory."""
    # Create some dummy files using pathlib
    Path(test_dir, 'test1.db').touch()
    Path(test_dir, 'test2.sqlite').touch()
    Path(test_dir, 'test3.sqlite3').touch()
    Path(test_dir, 'not_a_db.txt').touch()
    subdir = Path(test_dir, 'subdir')
    subdir.mkdir()
    Path(subdir, 'nested.db').touch()

    dbs = EasySQLite.list_databases(test_dir)
    # Get just the filenames for easier assertion
    db_filenames = [os.path.basename(p) for p in dbs]

    assert len(db_filenames) == 3
    assert 'test1.db' in db_filenames
    assert 'test2.sqlite' in db_filenames
    assert 'test3.sqlite3' in db_filenames
    assert 'not_a_db.txt' not in db_filenames
    assert 'nested.db' not in db_filenames # Should not be recursive

def test_list_databases_not_found():
    """Test listing databases in a non-existent directory."""
    with pytest.raises(FileNotFoundError):
        EasySQLite.list_databases('non_existent_directory_for_pytest')

def test_delete_database_force(other_db_path):
    """Test deleting a database file with confirm=False."""
    other_db = EasySQLite(other_db_path) # Create the file
    other_db.close()
    assert other_db_path.exists()

    result = EasySQLite.delete_database(other_db_path, confirm=False)
    assert result is True
    assert not other_db_path.exists()

def test_delete_database_confirm_yes(other_db_path, monkeypatch):
    """Test deleting a database file with confirmation 'y'."""
    other_db = EasySQLite(other_db_path)
    other_db.close()
    assert other_db_path.exists()

    # Mock input to return 'y'
    monkeypatch.setattr('builtins.input', lambda _: 'y')

    result = EasySQLite.delete_database(other_db_path, confirm=True)
    assert result is True
    assert not other_db_path.exists()

def test_delete_database_confirm_no(other_db_path, monkeypatch):
    """Test cancelling database deletion with confirmation 'n'."""
    other_db = EasySQLite(other_db_path)
    other_db.close()
    assert other_db_path.exists()

    # Mock input to return 'n'
    monkeypatch.setattr('builtins.input', lambda _: 'n')

    result = EasySQLite.delete_database(other_db_path, confirm=True)
    assert result is False
    assert other_db_path.exists() # File should still exist

def test_delete_database_not_exists(other_db_path):
    """Test deleting a non-existent database file."""
    assert not other_db_path.exists()
    result = EasySQLite.delete_database(other_db_path, confirm=False)
    assert result is False


# --- 5.2 Table Management Tests ---

def test_create_table_simple(db):
    """Test basic table creation."""
    result = db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
    assert result is True
    assert 'users' in db.list_tables()

def test_create_table_with_pk_constraint(db):
    """Test table creation with primary key and constraints."""
    result = db.create_table(
        'products',
        {'sku': 'TEXT', 'price': 'REAL NOT NULL'},
        primary_key='sku',
        constraints=['CHECK (price > 0)']
    )
    assert result is True
    desc = db.describe_table('products')
    sku_col = next((col for col in desc if col['name'] == 'sku'), None)
    price_col = next((col for col in desc if col['name'] == 'price'), None)
    assert sku_col['pk'] is True
    assert price_col['notnull'] is True
    # Cannot easily verify CHECK constraint via PRAGMA

def test_create_table_if_not_exists(db):
    """Test CREATE TABLE IF NOT EXISTS behavior."""
    assert db.create_table('users', {'id': 'INTEGER'}, if_not_exists=True) is True
    # Try creating again with IF NOT EXISTS (should succeed, return True)
    assert db.create_table('users', {'id': 'INTEGER'}, if_not_exists=True) is True
    # Try creating again *without* IF NOT EXISTS (should fail, raise TableError)
    with pytest.raises(TableError, match="already exists"):
         db.create_table('users', {'id': 'INTEGER'}, if_not_exists=False)

def test_create_table_invalid_name(db):
    """Test creating a table with an invalid name."""
    with pytest.raises(TableError, match="Invalid table name"):
        db.create_table('invalid-table-name', {'id': 'INTEGER'})
    with pytest.raises(TableError, match="Invalid column name"):
        db.create_table('users', {'invalid-col-name': 'TEXT'})
    with pytest.raises(ValueError, match="Columns dictionary cannot be empty"):
        db.create_table('no_cols', {})

def test_list_tables(db):
    """Test listing tables."""
    assert db.list_tables() == []
    db.create_table('table1', {'colA': 'TEXT'})
    assert db.list_tables() == ['table1']
    db.create_table('table2', {'colB': 'INTEGER'})
    tables = db.list_tables()
    assert 'table1' in tables
    assert 'table2' in tables
    assert len(tables) == 2

def test_describe_table(db):
    """Test describing a table."""
    db.create_table('items', {
        'item_id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
        'name': 'TEXT NOT NULL',
        'value': 'REAL DEFAULT 0.0'
    })
    desc = db.describe_table('items')
    assert len(desc) == 3

    id_col = desc[0]
    name_col = desc[1]
    value_col = desc[2]

    assert id_col['name'] == 'item_id'
    assert id_col['type'] == 'INTEGER'
    assert id_col['pk'] is True
    assert id_col['notnull'] is False # PK can be null before insert for AUTOINCREMENT

    assert name_col['name'] == 'name'
    assert name_col['type'] == 'TEXT'
    assert name_col['pk'] is False
    assert name_col['notnull'] is True

    assert value_col['name'] == 'value'
    assert value_col['type'] == 'REAL'
    assert value_col['pk'] is False
    assert value_col['notnull'] is False
    assert value_col['dflt_value'] == '0.0'

def test_describe_table_not_exists(db):
    """Test describing a non-existent table."""
    with pytest.raises(TableError, match="does not exist"):
        db.describe_table('non_existent_table')

def test_rename_table(db):
    """Test renaming a table."""
    db.create_table('old_table', {'col': 'TEXT'})
    assert db.rename_table('old_table', 'new_table') is True
    tables = db.list_tables()
    assert 'new_table' in tables
    assert 'old_table' not in tables

def test_rename_table_not_exists(db):
    """Test renaming a non-existent table."""
    with pytest.raises(TableError, match="does not exist"):
        db.rename_table('non_existent_table', 'new_name')

def test_delete_table_force(db):
    """Test deleting a table with force=True."""
    db.create_table('temp_table', {'col': 'TEXT'})
    assert 'temp_table' in db.list_tables()
    assert db.delete_table('temp_table', force=True) is True
    assert 'temp_table' not in db.list_tables()

def test_delete_table_confirm_yes(db, monkeypatch):
    """Test deleting a table with confirmation 'y'."""
    db.create_table('temp_table', {'col': 'TEXT'})
    monkeypatch.setattr('builtins.input', lambda _: 'y')
    assert db.delete_table('temp_table', force=False) is True
    assert 'temp_table' not in db.list_tables()

def test_delete_table_confirm_no(db, monkeypatch):
    """Test cancelling table deletion."""
    db.create_table('temp_table', {'col': 'TEXT'})
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    assert db.delete_table('temp_table', force=False) is False
    assert 'temp_table' in db.list_tables() # Should still exist

def test_delete_table_not_exists(db):
    """Test deleting a non-existent table (should succeed with IF EXISTS)."""
    # DROP TABLE IF EXISTS should not raise an error and return True
    assert db.delete_table('non_existent_table', force=True) is True


# --- 5.3 Column Management Tests ---

def test_add_column(db):
    """Test adding a column."""
    db.create_table('users', {'id': 'INTEGER'})
    assert db.add_column('users', 'email', 'TEXT', default_value='N/A') is True
    desc = db.describe_table('users')
    email_col = next((col for col in desc if col['name'] == 'email'), None)
    assert email_col is not None
    assert email_col['type'] == 'TEXT'
    assert email_col['dflt_value'] == "'N/A'" # Note: default values are stored as strings

def test_add_column_numeric_default(db):
    """Test adding a column with numeric default."""
    db.create_table('users', {'id': 'INTEGER'})
    assert db.add_column('users', 'score', 'INTEGER', default_value=0) is True
    desc = db.describe_table('users')
    score_col = next((col for col in desc if col['name'] == 'score'), None)
    assert score_col is not None
    assert score_col['type'] == 'INTEGER'
    assert score_col['dflt_value'] == '0'

def test_add_column_to_nonexistent_table(db):
    """Test adding a column to a non-existent table."""
    with pytest.raises(TableError, match="does not exist"):
         db.add_column('non_existent', 'new_col', 'TEXT')

@pytest.mark.skipif(not sqlite_version_ge(3, 25, 0), reason="RENAME COLUMN requires SQLite 3.25.0+")
def test_rename_column(db):
    """Test renaming a column (if supported)."""
    db.create_table('users', {'id': 'INTEGER', 'mail': 'TEXT'})
    assert db.rename_column('users', 'mail', 'email') is True
    desc = db.describe_table('users')
    col_names = [col['name'] for col in desc]
    assert 'email' in col_names
    assert 'mail' not in col_names

@pytest.mark.skipif(sqlite_version_ge(3, 25, 0), reason="Test only runs on SQLite < 3.25.0")
def test_rename_column_unsupported(db):
    """Test renaming a column when unsupported."""
    db.create_table('users', {'id': 'INTEGER', 'mail': 'TEXT'})
    with pytest.raises(NotImplementedError, match="RENAME COLUMN requires SQLite 3.25.0+"):
        db.rename_column('users', 'mail', 'email')

@pytest.mark.skipif(not sqlite_version_ge(3, 25, 0), reason="RENAME COLUMN requires SQLite 3.25.0+")
def test_rename_nonexistent_column(db):
    """Test renaming a non-existent column."""
    db.create_table('users', {'id': 'INTEGER'})
    with pytest.raises(ColumnError, match="does not exist"):
        db.rename_column('users', 'nonexistent', 'new_name')

@pytest.mark.skipif(not sqlite_version_ge(3, 35, 0), reason="DROP COLUMN requires SQLite 3.35.0+")
def test_delete_column(db):
    """Test deleting a column (if supported)."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'temp': 'BLOB'})
    assert db.delete_column('users', 'temp') is True
    desc = db.describe_table('users')
    col_names = [col['name'] for col in desc]
    assert 'temp' not in col_names
    assert len(col_names) == 2

@pytest.mark.skipif(sqlite_version_ge(3, 35, 0), reason="Test only runs on SQLite < 3.35.0")
def test_delete_column_unsupported(db):
    """Test deleting a column when unsupported."""
    db.create_table('users', {'id': 'INTEGER', 'temp': 'BLOB'})
    with pytest.raises(NotImplementedError, match="DROP COLUMN requires SQLite 3.35.0+"):
        db.delete_column('users', 'temp')

@pytest.mark.skipif(not sqlite_version_ge(3, 35, 0), reason="DROP COLUMN requires SQLite 3.35.0+")
def test_delete_nonexistent_column(db):
    """Test deleting a non-existent column."""
    db.create_table('users', {'id': 'INTEGER'})
    with pytest.raises(ColumnError, match="does not exist"): # Adjusted based on implementation detail
        db.delete_column('users', 'nonexistent')


# --- 5.4 Row Management Tests ---

def test_add_row(db):
    """Test adding a single row."""
    db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
    rowid = db.add_row('users', {'name': 'Alice'})
    assert isinstance(rowid, int)
    assert rowid > 0

    rows = db.get_rows('users')
    assert len(rows) == 1
    assert rows[0]['name'] == 'Alice'
    assert rows[0]['id'] == rowid

def test_add_row_violates_constraint(db):
    """Test adding a row that violates a UNIQUE constraint."""
    db.create_table('users', {'id': 'INTEGER', 'email': 'TEXT UNIQUE'})
    db.add_row('users', {'id': 1, 'email': 'test@example.com'})
    with pytest.raises(RowError, match="UNIQUE constraint"):
        db.add_row('users', {'id': 2, 'email': 'test@example.com'})

def test_add_rows(db):
    """Test adding multiple rows."""
    db.create_table('products', {'sku': 'TEXT', 'price': 'REAL'})
    data = [
        {'sku': 'A001', 'price': 10.99},
        {'sku': 'B002', 'price': 5.50},
    ]
    count = db.add_rows('products', data)
    assert count == 2
    assert db.count_rows('products') == 2

def test_add_rows_empty_list(db):
    """Test adding an empty list of rows."""
    db.create_table('products', {'sku': 'TEXT'})
    count = db.add_rows('products', [])
    assert count == 0

def test_add_rows_inconsistent_keys(db):
    """Test adding rows with inconsistent keys."""
    db.create_table('products', {'sku': 'TEXT', 'price': 'REAL'})
    data = [
        {'sku': 'A001', 'price': 10.99},
        {'sku': 'B002'}, # Missing price
    ]
    with pytest.raises(ValueError, match="Inconsistent keys"):
        db.add_rows('products', data)

def test_get_rows_all(db):
    """Test getting all rows."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
    db.add_rows('users', [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
    rows = db.get_rows('users')
    assert len(rows) == 2
    assert rows[0]['name'] == 'Alice'
    assert rows[1]['name'] == 'Bob'

def test_get_rows_specific_columns(db):
    """Test getting specific columns."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'email': 'TEXT'})
    db.add_row('users', {'id': 1, 'name': 'Alice', 'email': 'a@ex.com'})
    rows = db.get_rows('users', columns=['id', 'name'])
    assert len(rows) == 1
    assert 'id' in rows[0]
    assert 'name' in rows[0]
    assert 'email' not in rows[0]

def test_get_rows_condition_simple(db):
    """Test getting rows with a simple condition."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
    db.add_rows('users', [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
    rows = db.get_rows('users', condition={'name': 'Bob'})
    assert len(rows) == 1
    assert rows[0]['id'] == 2

def test_get_rows_condition_operators(db):
    """Test getting rows with different operators."""
    db.create_table('users', {'id': 'INTEGER', 'score': 'INTEGER', 'status': 'TEXT'})
    db.add_rows('users', [
        {'id': 1, 'score': 100, 'status': 'active'},
        {'id': 2, 'score': 150, 'status': 'active'},
        {'id': 3, 'score': 50, 'status': 'inactive'},
        {'id': 4, 'score': 150, 'status': None}
    ])
    # Greater than
    rows_gt = db.get_rows('users', condition={'score': 100}, operators={'score': '>'})
    assert len(rows_gt) == 2
    ids_gt = {r['id'] for r in rows_gt}
    assert ids_gt == {2, 4}
    # LIKE
    rows_like = db.get_rows('users', condition={'status': 'act%'}, operators={'status': 'LIKE'})
    assert len(rows_like) == 2
    # IS NULL
    rows_null = db.get_rows('users', condition={'status': None}, operators={'status': 'IS'})
    assert len(rows_null) == 1
    assert rows_null[0]['id'] == 4
    # IN
    rows_in = db.get_rows('users', condition={'id': [1, 3, 5]}, operators={'id': 'IN'})
    assert len(rows_in) == 2
    ids_in = {r['id'] for r in rows_in}
    assert ids_in == {1, 3}

def test_get_rows_condition_logic_or(db):
    """Test getting rows with OR logic."""
    db.create_table('users', {'id': 'INTEGER', 'score': 'INTEGER', 'status': 'TEXT'})
    db.add_rows('users', [
        {'id': 1, 'score': 100, 'status': 'active'},
        {'id': 2, 'score': 50, 'status': 'inactive'},
        {'id': 3, 'score': 100, 'status': 'inactive'},
    ])
    rows = db.get_rows('users', condition={'score': 100, 'status': 'inactive'}, condition_logic='OR')
    assert len(rows) == 3 # All rows match one or the other

def test_get_rows_order_by(db):
    """Test ordering results."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT'})
    db.add_rows('users', [{'id': 2, 'name': 'Bob'}, {'id': 1, 'name': 'Alice'}, {'id': 3, 'name': 'Charlie'}])
    rows_asc = db.get_rows('users', order_by='name ASC')
    assert [r['name'] for r in rows_asc] == ['Alice', 'Bob', 'Charlie']
    rows_desc = db.get_rows('users', order_by=['id DESC'])
    assert [r['id'] for r in rows_desc] == [3, 2, 1]

def test_get_rows_limit_offset(db):
    """Test limit and offset."""
    db.create_table('items', {'num': 'INTEGER'})
    db.add_rows('items', [{'num': i} for i in range(1, 11)]) # 1 to 10
    rows = db.get_rows('items', order_by='num', limit=3, offset=5)
    assert len(rows) == 3
    assert [r['num'] for r in rows] == [6, 7, 8]

def test_get_rows_offset_without_limit(db):
    """Test using offset without limit raises error."""
    db.create_table('items', {'num': 'INTEGER'})
    with pytest.raises(ValueError, match="OFFSET requires LIMIT"):
        db.get_rows('items', offset=5)

def test_update_rows(db):
    """Test updating rows."""
    db.create_table('users', {'id': 'INTEGER', 'name': 'TEXT', 'status': 'TEXT'})
    db.add_rows('users', [
        {'id': 1, 'name': 'Alice', 'status': 'pending'},
        {'id': 2, 'name': 'Bob', 'status': 'pending'},
        {'id': 3, 'name': 'Charlie', 'status': 'active'}
    ])
    affected = db.update_rows('users', {'status': 'approved'}, condition={'status': 'pending'})
    assert affected == 2
    rows = db.get_rows('users', condition={'status': 'approved'})
    assert len(rows) == 2
    ids = {r['id'] for r in rows}
    assert ids == {1, 2}

def test_update_rows_no_match(db):
    """Test updating rows when condition matches none."""
    db.create_table('users', {'id': 'INTEGER', 'status': 'TEXT'})
    db.add_row('users', {'id': 1, 'status': 'active'})
    affected = db.update_rows('users', {'status': 'inactive'}, condition={'id': 99})
    assert affected == 0

def test_update_rows_empty_data_or_condition(db):
    """Test update_rows with empty data or condition."""
    db.create_table('users', {'id': 'INTEGER'})
    with pytest.raises(ValueError, match="Data dictionary.*cannot be empty"):
        db.update_rows('users', {}, condition={'id': 1})
    with pytest.raises(ValueError, match="Condition dictionary cannot be empty"):
        db.update_rows('users', {'id': 2}, condition={})

def test_delete_rows(db):
    """Test deleting rows."""
    db.create_table('items', {'id': 'INTEGER', 'category': 'TEXT'})
    db.add_rows('items', [
        {'id': 1, 'category': 'A'}, {'id': 2, 'category': 'B'},
        {'id': 3, 'category': 'A'}, {'id': 4, 'category': 'C'}
    ])
    affected = db.delete_rows('items', condition={'category': 'A'})
    assert affected == 2
    assert db.count_rows('items') == 2
    remaining = db.get_rows('items')
    cats = {r['category'] for r in remaining}
    assert cats == {'B', 'C'}

def test_delete_rows_no_match(db):
    """Test deleting rows when condition matches none."""
    db.create_table('items', {'id': 'INTEGER'})
    db.add_row('items', {'id': 1})
    affected = db.delete_rows('items', condition={'id': 99})
    assert affected == 0
    assert db.count_rows('items') == 1

def test_delete_rows_requires_condition_or_force(db):
    """Test delete_rows safety measure (requires condition or force)."""
    db.create_table('items', {'id': 'INTEGER'})
    db.add_row('items', {'id': 1})
    # Should fail without condition and force_delete_all=False (default)
    with pytest.raises(ValueError, match="Condition dictionary cannot be empty"):
        db.delete_rows('items', condition={})
    with pytest.raises(ValueError, match="Condition dictionary cannot be empty"):
         db.delete_rows('items', condition=None)

def test_delete_rows_force_delete_all(db):
    """Test deleting all rows with force_delete_all=True."""
    db.create_table('items', {'id': 'INTEGER'})
    db.add_rows('items', [{'id': 1}, {'id': 2}])
    # Provide empty condition AND force_delete_all=True
    affected = db.delete_rows('items', condition={}, force_delete_all=True)
    assert affected == 2
    assert db.count_rows('items') == 0

def test_count_rows(db):
    """Test counting rows."""
    db.create_table('log', {'level': 'TEXT'})
    assert db.count_rows('log') == 0
    db.add_rows('log', [{'level': 'INFO'}, {'level': 'WARN'}, {'level': 'INFO'}])
    assert db.count_rows('log') == 3
    assert db.count_rows('log', condition={'level': 'INFO'}) == 2
    assert db.count_rows('log', condition={'level': 'ERROR'}) == 0

# --- 5.5 Joins Tests ---

def test_join_rows_left(db):
    """Test LEFT JOIN."""
    db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
    db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
    uid1 = db.add_row('users', {'name': 'Alice'})
    db.add_row('users', {'name': 'Bob'}) # Bob has no posts
    db.add_row('posts', {'user_id': uid1, 'title': 'Alice Post 1'})

    joins = [{'type': 'LEFT', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
    results = db.join_rows(
        base_table='users',
        joins=joins,
        columns=['users.name', 'posts.title'],
        order_by='users.name' # Use list or string
    )

    assert len(results) == 2
    # Alice has a post
    assert results[0]['name'] == 'Alice'
    assert results[0]['title'] == 'Alice Post 1'
    # Bob has no post, title should be None
    assert results[1]['name'] == 'Bob'
    assert results[1]['title'] is None

def test_join_rows_inner(db):
    """Test INNER JOIN."""
    db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
    db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
    uid1 = db.add_row('users', {'name': 'Alice'})
    db.add_row('users', {'name': 'Bob'}) # Bob has no posts
    db.add_row('posts', {'user_id': uid1, 'title': 'Alice Post 1'})

    joins = [{'type': 'INNER', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
    results = db.join_rows(
        base_table='users',
        joins=joins,
        columns=['users.name', 'posts.title']
    )

    assert len(results) == 1 # Only Alice should match
    assert results[0]['name'] == 'Alice'
    assert results[0]['title'] == 'Alice Post 1'

def test_join_rows_with_condition(db):
    """Test JOIN with a WHERE condition."""
    db.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'})
    db.create_table('posts', {'post_id': 'INTEGER PRIMARY KEY', 'user_id': 'INTEGER', 'title': 'TEXT'})
    uid1 = db.add_row('users', {'name': 'Alice'})
    uid2 = db.add_row('users', {'name': 'Bob'})
    db.add_row('posts', {'user_id': uid1, 'title': 'Post A'})
    db.add_row('posts', {'user_id': uid2, 'title': 'Post B'})

    joins = [{'type': 'INNER', 'target_table': 'posts', 'on': 'users.id = posts.user_id'}]
    results = db.join_rows(
        base_table='users',
        joins=joins,
        columns=['users.name', 'posts.title'],
        condition={'users.name': 'Bob'} # Filter condition using table prefix
    )

    assert len(results) == 1
    assert results[0]['name'] == 'Bob'
    assert results[0]['title'] == 'Post B'

def test_join_rows_invalid_type(db):
    """Test JOIN with an invalid join type."""
    db.create_table('users', {'id': 'INTEGER'})
    db.create_table('posts', {'post_id': 'INTEGER'})
    joins = [{'type': 'INVALID', 'target_table': 'posts', 'on': '1=1'}]
    with pytest.raises(JoinError, match="Unsupported JOIN type"):
         db.join_rows('users', joins)

# --- 5.6 Custom Query Tests ---

def test_execute_query_select(db):
    """Test executing a custom SELECT query."""
    db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
    db.add_rows('data', [{'key': 'A', 'value': 10}, {'key': 'B', 'value': 20}])
    result = db.execute_query("SELECT value FROM data WHERE key = ? ORDER BY value", ('B',))
    assert result['success'] is True
    assert len(result['data']) == 1
    assert result['data'][0]['value'] == 20
    assert result['rowcount'] == -1 # Rowcount often -1 for SELECT
    assert result['lastrowid'] is None
    assert result['error'] is None

def test_execute_query_insert(db):
    """Test executing a custom INSERT query."""
    db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
    result = db.execute_query("INSERT INTO data (key, value) VALUES (?, ?)", ('C', 30))
    assert result['success'] is True
    assert result['data'] == [] # Changed from None to [] based on _execute_sql impl
    assert result['rowcount'] == 1
    assert isinstance(result['lastrowid'], int)
    assert result['error'] is None
    # Verify insert
    rows = db.get_rows('data', condition={'key': 'C'})
    assert len(rows) == 1
    assert rows[0]['value'] == 30

def test_execute_query_update(db):
    """Test executing a custom UPDATE query."""
    db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
    db.add_row('data', {'key': 'D', 'value': 40})
    result = db.execute_query("UPDATE data SET value = ? WHERE key = ?", (45, 'D'))
    assert result['success'] is True
    assert result['data'] == [] # Changed from None to [] based on _execute_sql impl
    assert result['rowcount'] == 1
    assert result['lastrowid'] is None # lastrowid not applicable for UPDATE
    assert result['error'] is None
    # Verify update
    rows = db.get_rows('data', condition={'key': 'D'})
    assert rows[0]['value'] == 45

def test_execute_query_delete(db):
    """Test executing a custom DELETE query."""
    db.create_table('data', {'key': 'TEXT', 'value': 'INTEGER'})
    db.add_row('data', {'key': 'E', 'value': 50})
    result = db.execute_query("DELETE FROM data WHERE key = ?", ('E',))
    assert result['success'] is True
    assert result['data'] == [] # Changed from None to [] based on _execute_sql impl
    assert result['rowcount'] == 1
    assert result['lastrowid'] is None # lastrowid not applicable for DELETE
    assert result['error'] is None
    # Verify delete
    assert db.count_rows('data') == 0

def test_execute_query_invalid_sql(db):
    """Test executing invalid SQL."""
    result = db.execute_query("SELECT * FROM non_existent_table")
    assert result['success'] is False
    assert result['data'] is None # Or [] depending on exact error path
    assert 'no such table' in result['error'].lower() # Check for common error message

    result_syntax = db.execute_query("SELEC * FROM data") # Intentional syntax error
    assert result_syntax['success'] is False
    assert result_syntax['data'] is None # Or []
    assert 'syntax error' in result_syntax['error'].lower()

# Example of how to run these tests using pytest:
# 1. Make sure pytest is installed (`pip install pytest`).
# 2. Save this code as `test_easysqlite.py` inside a `tests` directory.
# 3. Ensure the `easysqlite` package directory is in the same parent directory or installed.
# 4. Navigate to the parent directory (containing `easysqlite` and `tests`) in your terminal.
# 5. Run the command: `pytest`
