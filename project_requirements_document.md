**Product Requirements Document: EasySQLite Python Library**

**Version:** 1.0
**Date:** 2025-04-18
**Status:** Draft

**1. Introduction**

* **1.1. Overview:** EasySQLite is envisioned as a lightweight, intuitive Python library that acts as a wrapper around Python's built-in `sqlite3` module. Its primary purpose is to significantly simplify common database operations for users who are not familiar with SQL syntax or find the standard `sqlite3` API verbose for simple tasks.
* **1.2. Problem:** Working directly with SQLite in Python requires knowledge of SQL commands (`CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `JOIN`, `ALTER`, etc.) and careful handling of connections, cursors, transactions, and data type conversions. This presents a barrier for beginners, data analysts, or developers needing simple, local data persistence without a steep learning curve.
* **1.3. Vision:** To provide a Pythonic, user-friendly interface for SQLite databases, enabling rapid development and easy data manipulation through simple function calls, while handling common boilerplate and basic safety concerns internally.

**2. Goals & Objectives**

* **2.1. Primary Goals:**
    * Abstract away the complexity of common SQL commands for SQLite.
    * Provide an intuitive, high-level API using Python functions and data structures (dictionaries, lists).
    * Reduce the amount of boilerplate code required for basic database interactions.
    * Offer basic protection against SQL injection for data values passed into the library's methods.
* **2.2. Secondary Goals:**
    * Simplify the management of database files and connections.
    * Allow execution of custom SQL for advanced use cases not covered by the wrappers.
    * Be easily installable via PyPI.
    * Provide clear documentation and usage examples.

**3. Target Audience**

* **3.1. Primary:** Python developers (beginners to intermediate), data analysts, students, hobbyists, and scripters who need simple, local database storage and prefer a Pythonic interface over writing raw SQL.
* **3.2. Secondary:** Experienced developers looking for a quick way to perform simple SQLite tasks in scripts or prototypes without the overhead of a full ORM.

**4. Scope**

* **4.1. In Scope:**
    * Connecting to/creating SQLite database files.
    * Listing available database files in a directory.
    * Deleting database files (with confirmation).
    * CRUD operations for Tables (Create, List, Describe, Rename, Delete).
    * CRUD operations for Columns (Add, Rename, Delete - respecting SQLite limitations).
    * CRUD operations for Rows (Add single/multiple, Get with filtering/ordering/limiting, Update, Delete, Count).
    * Support for common SQL JOIN types (`INNER`, `LEFT`, `RIGHT`, `FULL OUTER` - where supported by SQLite) via a simplified function interface.
    * A function to execute arbitrary, user-provided SQL queries safely (using parameterization where applicable).
    * Use of Python dictionaries and lists for data input/output.
    * Context manager support (`with` statement) for automatic connection management.
    * Basic error handling and logging.
    * Packaging and distribution via PyPI.
    * Type hinting for better code analysis and developer experience.
* **4.2. Out of Scope:**
    * Object-Relational Mapping (ORM) features (mapping database rows directly to Python objects).
    * Advanced SQL features not easily abstracted (e.g., complex triggers, window functions, recursive CTEs - unless used via `execute_query`).
    * Database server features (e.g., handling high-concurrency multi-user scenarios beyond `check_same_thread=False`, replication, user management).
    * Support for database backends other than SQLite.
    * Complex database schema migration tools.
    * Graphical User Interface (GUI).
    * Performance tuning beyond standard SQLite practices implemented internally.

**5. Functional Requirements**

The library will be implemented primarily as a class (e.g., `EasySQLite`) instantiated with a database file path.

* **5.1. Database Management:**
    * **5.1.1. `__init__(db_path)`:** Constructor. Establishes connection to the SQLite file at `db_path`. Creates the file and any necessary directories if they don't exist. Sets up connection/cursor.
    * **5.1.2. `close()`:** Explicitly closes the database connection.
    * **5.1.3. `list_databases(directory='.') -> List[str]`:** (Static or instance method) Returns a list of file paths ending in `.db` or `.sqlite` (case-insensitive) within the specified directory.
    * **5.1.4. `delete_database(db_path) -> bool`:** (Static or instance method) Deletes the specified SQLite database file from the filesystem. *Must* prompt the user for confirmation before deletion. Returns `True` on success, `False` otherwise.
    * **5.1.5. Context Manager (`__enter__`, `__exit__`):** Enables usage via `with EasySQLite(...) as db:`. Ensures `close()` is called automatically. Manages commit/rollback on exit (commit on success, rollback on exception).

* **5.2. Table Management (CRUD):**
    * **5.2.1. `create_table(table_name: str, columns: Dict[str, str], primary_key: Optional[Union[str, List[str]]] = None, constraints: Optional[List[str]] = None) -> bool`:** Creates a table named `table_name` if it doesn't exist.
        * `columns`: Dictionary mapping column names to their SQLite types (e.g., `'name': 'TEXT', 'age': 'INTEGER'`).
        * `primary_key`: Optional string or list of strings specifying the primary key column(s). Can include standard SQLite definitions like `INTEGER PRIMARY KEY AUTOINCREMENT` directly in the `columns` dict type.
        * `constraints`: Optional list of table-level constraint strings (e.g., `['UNIQUE (email)', 'CHECK (age > 0)']`).
        * Returns `True` on success or if table already exists, `False` on error.
    * **5.2.2. `list_tables() -> List[str]`:** Returns a list of all table names in the current database.
    * **5.2.3. `describe_table(table_name: str) -> List[Dict]`:** Returns detailed information about each column in the table (name, type, nullability, default value, primary key status). Uses `PRAGMA table_info`. Output format should be a list of dictionaries.
    * **5.2.4. `rename_table(old_name: str, new_name: str) -> bool`:** Renames an existing table. Returns `True` on success, `False` otherwise.
    * **5.2.5. `delete_table(table_name: str) -> bool`:** Deletes (drops) the specified table. *Should* prompt for confirmation or have a `force=True` flag. Returns `True` on success, `False` otherwise.

* **5.3. Column Management (CRUD - via ALTER TABLE):**
    * **5.3.1. `add_column(table_name: str, column_name: str, column_type: str, default_value: Optional[Any] = None) -> bool`:** Adds a new column to an existing table. Allows specifying a default value. Returns `True` on success.
    * **5.3.2. `rename_column(table_name: str, old_name: str, new_name: str) -> bool`:** Renames an existing column. *Note:* Requires SQLite 3.25.0+. The implementation should check SQLite version or handle potential errors gracefully. Returns `True` on success.
    * **5.3.3. `delete_column(table_name: str, column_name: str) -> bool`:** Deletes (drops) an existing column. *Note:* Requires SQLite 3.35.0+. The library might need to implement the complex copy/recreate workaround for older versions or clearly document the limitation. Returns `True` on success.

* **5.4. Row Management (CRUD):**
    * **5.4.1. `add_row(table_name: str, data: Dict[str, Any]) -> Optional[int]`:** Inserts a single row into the table. `data` is a dictionary mapping column names to values. Returns the `rowid` of the inserted row, or `None` on failure.
    * **5.4.2. `add_rows(table_name: str, data_list: List[Dict[str, Any]]) -> int`:** Inserts multiple rows efficiently. `data_list` is a list of dictionaries. Returns the number of rows successfully inserted. Uses `executemany`.
    * **5.4.3. `get_rows(table_name: str, columns: List[str] = ['*'], condition: Optional[Dict[str, Any]] = None, condition_logic: str = 'AND', operators: Optional[Dict[str, str]] = None, order_by: Optional[Union[str, List[str]]] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict]`:** Retrieves rows matching criteria.
        * `columns`: List of columns to select (defaults to all).
        * `condition`: Dictionary for basic `WHERE` clause (e.g., `{'name': 'Alice', 'status': 1}`).
        * `condition_logic`: How to combine conditions ('AND' or 'OR'). Defaults to 'AND'.
        * `operators`: Optional dictionary mapping columns in `condition` to operators other than `=` (e.g., `{'age': '>', 'name': 'LIKE'}`). Defaults to `=` for all.
        * `order_by`: Column name string (e.g., `'name ASC'`) or list of strings for ordering.
        * `limit`, `offset`: For pagination.
        * Returns a list of dictionaries, each representing a row. Returns empty list if no matches.
    * **5.4.4. `update_rows(table_name: str, data: Dict[str, Any], condition: Dict[str, Any], condition_logic: str = 'AND', operators: Optional[Dict[str, str]] = None) -> int`:** Updates rows matching the `condition`. `data` contains columns/values to set. Returns the number of rows affected. `condition_logic` and `operators` work as in `get_rows`.
    * **5.4.5. `delete_rows(table_name: str, condition: Dict[str, Any], condition_logic: str = 'AND', operators: Optional[Dict[str, str]] = None) -> int`:** Deletes rows matching the `condition`. Requires a non-empty condition dictionary for safety, unless a `force_delete_all=True` flag is added. Returns the number of rows affected.
    * **5.4.6. `count_rows(table_name: str, condition: Optional[Dict[str, Any]] = None, condition_logic: str = 'AND', operators: Optional[Dict[str, str]] = None) -> int`:** Returns the count of rows matching the condition.

* **5.5. Joins:**
    * **5.5.1. `join_rows(base_table: str, joins: List[Dict], columns: List[str] = ['*'], condition: Optional[Dict[str, Any]] = None, condition_logic: str = 'AND', operators: Optional[Dict[str, str]] = None, order_by: Optional[Union[str, List[str]]] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict]`:** Performs JOIN operations.
        * `base_table`: The starting table (FROM clause).
        * `joins`: A list of dictionaries, each defining a join: `{'type': 'LEFT', 'target_table': 'orders', 'on': 'users.id = orders.user_id'}`. `type` can be `INNER`, `LEFT` (SQLite supports limited `RIGHT`/`FULL` via `LEFT`). `on` is the join condition string.
        * Other parameters (`columns`, `condition`, etc.) work similarly to `get_rows`, but column names in conditions/ordering might need table prefixes (e.g., `'users.name'`). Columns selected should also ideally allow prefixes.
        * Returns a list of dictionaries representing the joined rows.

* **5.6. Custom Query:**
    * **5.6.1. `execute_query(sql: str, params: Optional[Union[Tuple, Dict]] = None) -> Dict`:** Executes a raw SQL query provided by the user.
        * Uses parameterization (`?` or `:named` style) via the `params` argument to prevent injection if `params` are used.
        * *Must clearly document* the security implications if the user builds `sql` strings with external input without using `params`.
        * Returns a dictionary containing:
            * `success`: Boolean indicating if execution succeeded.
            * `data`: List of dictionaries (for SELECT queries, using `Workspaceall()`).
            * `rowcount`: Number of rows affected (for INSERT, UPDATE, DELETE).
            * `lastrowid`: Last inserted row ID (if applicable).
            * `error`: Error message string if `success` is False.

**6. Non-Functional Requirements**

* **6.1. Usability:**
    * API should be intuitive and require minimal learning for users familiar with Python basics.
    * Method and parameter names should be clear and descriptive.
    * Comprehensive `README.md` with installation guide and clear usage examples for all major features.
    * Docstrings for all public classes and methods.
* **6.2. Reliability:**
    * Gracefully handle common SQLite errors (e.g., table not found, unique constraint violation) and provide informative error messages (via logging and return values/exceptions - TBD).
    * Ensure database connections are properly managed (opened, closed, context managed).
    * Modifying operations should be atomic (implicitly committed on success, rolled back on error).
* **6.3. Performance:**
    * Wrapper functions should aim to minimize overhead compared to direct `sqlite3` calls.
    * Bulk operations (`add_rows`) should leverage `executemany` for efficiency.
    * No guarantees on the performance of complex user-provided queries or joins beyond underlying SQLite capabilities.
* **6.4. Security:**
    * Internal implementation MUST use parameterized queries for all user-supplied *data values* passed into wrapper methods to prevent SQL injection.
    * Documentation must warn about potential injection risks if users construct table/column names from untrusted input.
    * Documentation must warn about risks when using `execute_query` without parameterization.
* **6.5. Maintainability:**
    * Codebase should be well-structured, commented, and follow PEP 8 guidelines.
    * Include a test suite (e.g., using `pytest`) covering core functionality and edge cases.
* **6.6. Portability:**
    * The library should work on all major operating systems (Windows, macOS, Linux) where Python and SQLite are supported.
    * Package dependencies should be minimal (ideally only standard library).

**7. Design Considerations**

* **7.1. API Style:** Primarily object-oriented (class-based).
* **7.2. Error Handling:** Define a consistent strategy: Return status codes/special values (e.g., `None`, `-1`, `False`) and log errors OR raise custom exceptions. (Initial lean towards return codes + logging for simplicity, but exceptions are more Pythonic - needs final decision).
* **7.3. JOIN Interface:** The structure for defining joins in `join_rows` needs careful design for usability vs. flexibility. The proposed list of dictionaries seems feasible.
* **7.4. SQLite Version Dependencies:** Features like `RENAME COLUMN` and `DROP COLUMN` depend on the underlying SQLite version. The library must either check the version and adapt, document the minimum required version, or gracefully handle the `OperationalError` if the feature is unavailable.

**8. Release Criteria & Success Metrics**

* **8.1. Definition of Done (v1.0):**
    * All Functional Requirements listed in section 5 are implemented.
    * Code is reviewed and adheres to basic quality standards.
    * Comprehensive test suite passes (>80% coverage for core features).
    * `README.md` and docstrings are complete and accurate.
    * Package can be successfully built and installed from PyPI/TestPyPI.
* **8.2. Success Metrics:**
    * PyPI download count over time.
    * Number of GitHub stars/forks (if applicable).
    * Low volume of bug reports related to core functionality.
    * Qualitative feedback indicating ease of use.

**9. Future Considerations**

* Optional exception-based error handling mode.
* More sophisticated query building capabilities (e.g., chaining methods, complex logical operators).
* Helper functions for common PRAGMA commands.
* Basic schema migration support.
* Asynchronous support (`aiosqlite`).
* Support for specific SQLite extensions (JSON1, FTS5, etc.) via dedicated methods.

**10. Open Issues**

* Final decision on error handling strategy (return codes vs. exceptions).
* Finalize the exact structure and validation for the `joins` parameter in `join_rows`.
* How to handle SQLite version dependencies for `ALTER TABLE` operations (documentation, runtime check, or workaround implementation)?
* Should destructive operations like `delete_table` and `delete_database` always prompt, or rely on a `force=True` flag?

---