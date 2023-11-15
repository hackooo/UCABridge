from services.servicenow_api import ServiceNowAPI
from services.splunk_api import SplunkAPI
from database import Database

class SchemaCreator:
    def __init__(self, config, logger):
        # Store the configuration and logger instances
        self.config = config
        self.logger = logger

        # Initialize the Database object for database operations
        self.database = Database(config, logger)

    def create_schemas(self):
        # Create schemas for ServiceNow and Splunk, and potentially other services
        self.create_dynamic_schemas('ServiceNow')
        self.create_dynamic_schemas('Splunk')
        self.create_dynamic_schemas('Yaml')
        self.database.create_users_table()
        self.database.insert_test_account()
        # Additional services can be added here

    def create_dynamic_schemas(self, service_name):
        # Delegate the creation of dynamic schemas to the Database object
        self.database.create_dynamic_schemas(service_name, self.config, self.logger)
