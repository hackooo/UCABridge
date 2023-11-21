import os
import subprocess
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch

class Database:
    def __init__(self, config, logger):
        # Store the configuration and logger instances
        self.config = config
        self.logger = logger

        # Connect to the database
        self.conn = self._connect()

    def _connect(self):
        # Try to establish a connection to the database
        try:
            return psycopg2.connect(
                dbname=self.config.get('Database', 'dbname'),
                user=self.config.get('Database', 'user'),
                password=self.config.get('Database', 'password'),
                host=self.config.get('Database', 'host')
            )
        except psycopg2.DatabaseError as e:
            # Log any database connection errors and re-raise the exception
            self.logger.error(f"Database connection failed: {e}")
            raise

    def store_data(self, table, fields, record):
        # Prepare columns and values for the SQL INSERT query
        columns = [sql.Identifier(field) for field in fields]
        values = [record.get(field) for field in fields]

        # Construct the SQL query for inserting data
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(', ').join(columns),
            sql.SQL(', ').join(sql.Placeholder() * len(columns))
        )

        # Execute the query and handle any exceptions
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, values)
                self.conn.commit()
        except psycopg2.DatabaseError as e:
            # Log any errors during the database operation and rollback the transaction
            self.logger.error(f"Error during database operation: {e}")
            self.conn.rollback()


    def view_data(self, table, fields, conditions=None, join=None):
        # Splitting the table and column names
        columns = [sql.SQL("{}.{}").format(sql.Identifier(field.split('.')[0]), sql.Identifier(field.split('.')[1])) if '.' in field else sql.Identifier(field) for field in fields]

        # Construct the basic SQL query for selecting data
        query = sql.SQL("SELECT {} FROM {}").format(sql.SQL(', ').join(columns), sql.Identifier(table))
        
        # Add JOIN clause if provided
        if join:
            query = sql.SQL("{} {}").format(query, sql.SQL(join))

        # Add conditions to the query if any
        if conditions:
            condition_statements = [sql.SQL("{} = %s").format(sql.Identifier(key)) for key in conditions]

            query = sql.SQL("{} WHERE {}").format(query, sql.SQL(' AND ').join(condition_statements))

        # Execute the query and return the results
        try:
            with self.conn.cursor() as cursor:
             #   print(conditions)
                cursor.execute(query, list(conditions.values()) if conditions else None)
                # Fetch column names
                col_names = [desc[0] for desc in cursor.description]
                # Fetch all rows and convert each row to a dictionary
                rows = cursor.fetchall()
                result = [dict(zip(col_names, row)) for row in rows]
                print(f"rows: {rows}")
                return result
        except psycopg2.DatabaseError as e:
            self.logger.error(f"Error during select operation: {e}")
            return None



    def create_schema(self, table, field_definitions, unique_key=None):
        # Create a database schema (table) if it doesn't exist
        try:
            with self.conn.cursor() as cursor:
                # Construct the SQL query for creating the table
                schema_creation_query = f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id SERIAL PRIMARY KEY,
                        {', '.join(field_definitions)}
                    """

                # Add a unique constraint if a unique key is provided
                if unique_key:
                    schema_creation_query += f",\nCONSTRAINT {table}_{unique_key}_unique UNIQUE ({unique_key})"

                schema_creation_query += ");"

                # Execute the schema creation query
                cursor.execute(schema_creation_query)
                self.conn.commit()
                self.logger.info(f"Database schema for table '{table}' created successfully.")
        except psycopg2.DatabaseError as e:
            # Log any errors during schema creation and rollback the transaction
            self.logger.error(f"Error creating database schema for table '{table}': {e}")
            self.conn.rollback()

    def create_dynamic_schemas(self, config_section, config, logger):
        # Create database schemas based on the provided configuration section
        i = 1
        while True:
            table_key = f'{config_section}_table_{i}'
            fields_key = f'{config_section}_fields_{i}'
            unique_key_option = f'{config_section}_unique_key_{i}'

            # Break the loop if there is no more configuration for tables
            if not config.has_option(config_section, table_key):
                break

            # Extract table name, fields, and unique key from the configuration
            table = config.get(config_section, table_key)
            fields = config.get(config_section, fields_key).split(', ')
            unique_key = config.get(config_section, unique_key_option) if config.has_option(config_section, unique_key_option) else None
            field_definitions = [f"{field.split(':')[0]} {field.split(':')[1]}" for field in fields]
            
            # Create the schema for each table
            self.create_schema(table, field_definitions, unique_key)
            i += 1

    def upsert_data(self, table, fields, record, unique_keys):
        # Prepare the SQL query for inserting or updating (upsert) data
        fields = [item.replace('"', '') for item in fields]
        columns = [sql.Identifier(field) for field in fields]
        values = [record.get(field) for field in fields]

        # Prepare the SET clause for the fields that are not unique keys
        set_clause = sql.SQL(', ').join([
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(field), sql.Identifier(field))
            for field in fields if field not in unique_keys
        ])

        # Identify the conflict target columns (unique keys)
        conflict_target = sql.SQL(', ').join([sql.Identifier(key) for key in unique_keys])

        # Construct the SQL query for upsert
        query = sql.SQL("""
            INSERT INTO {} ({})
            VALUES ({})
            ON CONFLICT ({})
            DO UPDATE SET {}
        """).format(
            sql.Identifier(table),
            sql.SQL(', ').join(columns),
            sql.SQL(', ').join([sql.Placeholder()] * len(columns)),
            conflict_target,
            set_clause
        )
        print(query)
        # Execute the upsert query and handle any exceptions
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, values)
                self.conn.commit()
        except psycopg2.DatabaseError as e:
            # Log any errors during the upsert operation and rollback the transaction
            self.logger.error(f"Error during upsert operation: {e}")
            self.conn.rollback()


    def backup_database(self):
        # Get backup file path and filename from configuration
        backup_path = self.config.get('Backup', 'backup_path')
        backup_filename = self.config.get('Backup', 'backup_filename')
        backup_file = os.path.join(backup_path, backup_filename)

        # Command for PostgreSQL database backup
        backup_cmd = f"pg_dump -h {self.config.get('Database', 'host')} -U {self.config.get('Database', 'user')} {self.config.get('Database', 'dbname')} > {backup_file}"

        # Execute the backup command
        try:
            subprocess.run(backup_cmd, shell=True, check=True)
            self.logger.info(f"Database backup completed successfully and stored in {backup_file}.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Database backup failed: {e}")


    def validate_login(self, username, password):
        """ Validate user login """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
                return cursor.fetchone()
        except psycopg2.DatabaseError as e:
            self.logger.error(f"Error validating login for {username}: {e}")

    def insert_test_account(self):
            """ Insert a test account into the users table """
            try:
                # Read test account details from the configuration
                test_name = self.config.get('TestAccount', 'name')
                test_username = self.config.get('TestAccount', 'username')
                test_password = self.config.get('TestAccount', 'password')
                test_group = self.config.get('TestAccount', 'group_id')
                with self.conn.cursor() as cursor:
                    # Insert a test account
                    cursor.execute(
                        "INSERT INTO users(username, password, name, group_id) VALUES(%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                        (test_username, test_password, test_name, test_group)
                    )
                    self.conn.commit()
                    self.logger.info("Test account inserted or already exists in the users table.")
            except psycopg2.DatabaseError as e:
                self.logger.error(f"Error inserting test account: {e}")
                self.conn.rollback()

    def create_users_table(self):
        """ Create the users table if it doesn't exist """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        password VARCHAR(255) NOT NULL,
                        name VARCHAR(255) UNIQUE NOT NULL,
                        group_id VARCHAR(255) UNIQUE NOT NULL      
                    );
                """)
                self.conn.commit()
                self.logger.info("Users table created successfully.")
        except psycopg2.DatabaseError as e:
            self.logger.error(f"Error creating users table: {e}")
            self.conn.rollback()

    def execute_query(self, query):
        """ Execute an arbitrary SQL query and return the results if it's a SELECT query. """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query)
                # Check if it's a SELECT query
                if query.strip().lower().startswith('select'):
                    results = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return results, columns
                else:
                    self.conn.commit()
                    return None, None
        except psycopg2.DatabaseError as e:
            self.logger.error(f"Error executing query: {e}")
            self.conn.rollback()
            raise

    def get_default_select_queries(self, config):
            default_queries = []
            for section in config.sections():
                for key, value in config.items(section):
                    if key.startswith('servicenow_table_') or key.startswith('yaml_table_') or key.startswith('splunk_table_'):
                        # Safe construction of the query
                        query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(value)).as_string(self.conn)
                        default_queries.append(query)
            return default_queries
    

    def update_task(self, sys_id, new_state, new_work_notes):
        update_query = """
        UPDATE snow_tasks
        SET state = %s, work_notes = %s
        WHERE sys_id = %s
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(update_query, (new_state, new_work_notes, sys_id))
                self.conn.commit()
        except psycopg2.DatabaseError as e:
            self.logger.error(f"Error in update_task: {e}")
            self.conn.rollback()
