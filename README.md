# EasySQLite

**Version: 1.0.0**

A lightweight, intuitive Python library that acts as a wrapper around Python's built-in `sqlite3` module. Its primary purpose is to significantly simplify common database operations for users who are not familiar with SQL syntax or find the standard `sqlite3` API verbose for simple tasks.

## Problem Solved

Working directly with `sqlite3` requires SQL knowledge and careful handling of connections, cursors, transactions, and data types. EasySQLite provides a Pythonic interface, reducing boilerplate and abstracting common SQL commands.

## Features (v1.0)

* Connect to/create SQLite database files easily.
* Context manager (`with` statement) for automatic connection handling (commit/rollback, close).
* Conforms with the Python ideology, as this is more **python like** than using sql queries.
* List and delete database files (with confirmation).
* Table CRUD: Create, List, Describe, Rename, Delete (with confirmation/force flag).
* Column CRUD (via `ALTER TABLE`): Add, Rename\*, Delete\* (\*requires modern SQLite versions).
* Row CRUD: Add single/multiple rows (using dictionaries), Get rows with filtering/ordering/limiting, Update rows, Delete rows (with safety checks), Count rows.
* Simplified `JOIN` operations (INNER, LEFT, CROSS).
* Execute arbitrary SQL queries safely using parameterization.
* Basic logging for operations and errors.
* Type hinting for better developer experience.

## Installation

```bash
pip install easysqlite-lib 
````

## Quickstart

```python
from easysqlite import EasySQLite, EasySQLiteError

DB_FILE = 'my_app_data.db'

try:
    # Use the context manager for safe connection handling
    with EasySQLite(DB_FILE) as db:
        # Create a table if it doesn't exist
        db.create_table(
            'users',
            {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT', 'email': 'TEXT UNIQUE'}
        )

        # Add some data
        user_id = db.add_row('users', {'name': 'Alice', 'email': 'alice@example.com'})
        db.add_rows('users', [
            {'name': 'Bob', 'email': 'bob@example.com'},
            {'name': 'Charlie', 'email': 'charlie@example.com'}
        ])

        # Retrieve data
        print("All users:")
        all_users = db.get_rows('users')
        for user in all_users:
            print(user) # Rows are dict-like

        print("\nUser with ID 1:")
        user1 = db.get_rows('users', condition={'id': 1})
        print(user1)

        # Update data
        db.update_rows('users', {'email': 'robert@example.com'}, condition={'name': 'Bob'})
        print("\nBob's updated record:")
        print(db.get_rows('users', condition={'name': 'Bob'}))

        # Count rows
        print(f"\nTotal users: {db.count_rows('users')}")

        # Delete data
        db.delete_rows('users', condition={'name': 'Charlie'})
        print(f"\nTotal users after delete: {db.count_rows('users')}")

        # Custom query (safe with parameters)
        print("\nUsers with example.com emails (custom query):")
        result = db.execute_query("SELECT name FROM users WHERE email LIKE ?", ('%@example.com',))
        if result['success']:
            print(result['data'])

except EasySQLiteError as e:
    print(f"Database operation failed: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

```

## Error Handling

The library primarily uses return values (like `bool`, `int`, `List`, `Optional[int]`) to indicate success or simple results. For more significant errors during operations (e.g., SQL syntax errors, constraint violations, non-existent tables/columns where not expected, invalid input), it raises custom exceptions derived from `EasySQLiteError` (e.g., `TableError`, `RowError`, `QueryError`). Check the specific method docstrings for details on potential exceptions.

## Security

  * **SQL Injection:** The library uses parameterization (`?` placeholders) internally for all methods that accept data values (`add_row`, `add_rows`, `get_rows`, `update_rows`, `delete_rows`, `execute_query` with `params`). This protects against SQL injection *for data values*.
  * **Identifiers:** Table names and column names provided by the user are generally assumed to be safe (developer-provided). **Do not construct table or column names directly from untrusted external input**, as this library does not sanitize identifiers.
  * **`execute_query`:** Be extremely careful when using `execute_query`. If you build the SQL string dynamically using external input *without* using the `params` argument for that input, you risk SQL injection.

## Limitations & SQLite Versions

  * **RENAME COLUMN:** Requires SQLite `3.25.0+`. Raises `NotImplementedError` on older versions.
  * **DROP COLUMN:** Requires SQLite `3.35.0+`. Raises `NotImplementedError` on older versions. The complex copy/recreate workaround is *not* implemented.
  * **JOINs:** The `on` condition string in `join_rows` must be provided correctly, including necessary table prefixes (`table.column`). The library does not parse or automatically qualify these.
  * **Error Handling Strategy:** Uses a mix of return values and custom exceptions. See method docstrings.
  * **Concurrency:** Uses `check_same_thread=False` for basic multi-threaded use cases but doesn't provide advanced concurrency control beyond standard SQLite capabilities. Not suitable for high-concurrency server applications without careful design.

## Contributing

Contributions are welcome\! Please open an issue or submit a pull request on GitHub. (Link to repo)

## License

This project is licensed under the Apache License, Version 2.0 - see the [LICENSE](LICENSE) file for details.

---
