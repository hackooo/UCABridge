from config import Config
from logger import Logger
from services.servicenow_api import ServiceNowAPI
from services.splunk_api import SplunkAPI
from services.yaml import Yaml
from schema_creator import SchemaCreator
from database import Database
import threading
import time

config = Config('settings.cfg')
logger = Logger()
database = Database(config, logger)
schema_creator = SchemaCreator(config, logger)

def create_schemas():
    schema_creator.create_schemas()

def servicenow():
    servicenow_api = ServiceNowAPI(config, logger)
    for ticket_type in servicenow_api.ticket_info.keys():
        servicenow_api.fetch_and_store_data(ticket_type)

def splunk():
    splunk_api = SplunkAPI(config, logger)
    for query_key in config.options('Splunk'):
        if query_key.startswith('splunk_query_'):
            splunk_api.execute_and_store_query(query_key)

def backup_db():
    database.backup_database()

def generate_yaml():
    yaml_job = Yaml(config, logger)
    yaml_job.generate_yaml_files()


def run_web():
    from web.web_app import start_web_app
    start_web_app()

def stop_servicenow():
    stop_service('servicenow')

def stop_splunk():
    stop_service('splunk')

scheduled_services = {}

def schedule_service(service_function, service_name, interval_minutes=1):
    
    def run_task():
        print()
        while service_name in scheduled_services:
            print(service_name)
            try:
                logger.info(f"Executing service: {service_name}")
                service_function()
            except Exception as e:
                logger.error(f"Error in service {service_name}: {e}")
            finally:
                logger.info(f"Service {service_name} completed. Sleeping for {interval_minutes} minute(s).")
                time.sleep(interval_minutes * 10)  # Sleep for interval_minutes

    # Stop the service if it's already running
    stop_service(service_name)

    # Start the new service thread
    thread = threading.Thread(target=run_task)
    thread.daemon = True
    thread.start()

    # Store the thread
    scheduled_services[service_name] = thread

def stop_service(service_name):
    if service_name in scheduled_services:
        # Remove the service from the dictionary to stop the loop
        del scheduled_services[service_name]
        logger.info(f'Stopping service: {service_name}')