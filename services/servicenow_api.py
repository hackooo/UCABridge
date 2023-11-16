from api_base import APIBase
from database import Database
from datetime import datetime

class ServiceNowAPI(APIBase):
    def __init__(self, config, logger):
        # Call the constructor of the parent class (APIBase)
        super().__init__(config, logger)

        # Initialize the Database object for data operations
        self.database = Database(config, logger)

        # Extract information about ServiceNow tickets
        self.ticket_info = self._extract_ticket_info()

        # Log that the ServiceNow API has been initialized
        self.logger.info("ServiceNowAPI initialized")

    def _extract_ticket_info(self):
        self.logger.info("Extracting ticket information from ServiceNow configuration")
        ticket_info = {}
        for option in self.config.options('ServiceNow'):
            if option.startswith('servicenow_table_'):
                index = option.split('_')[-1]
                table = self.config.get('ServiceNow', f'servicenow_table_{index}')
                endpoint = self.config.get('ServiceNow', f'servicenow_endpoint_{index}')

                # Handling the absence of certain configuration values
                fields_key = f'servicenow_fields_{index}'
                unique_key_key = f'servicenow_unique_key_{index}'
                fields = self.config.get('ServiceNow', fields_key) if self.config.has_option('ServiceNow', fields_key) else None
                unique_key = self.config.get('ServiceNow', unique_key_key) if self.config.has_option('ServiceNow', unique_key_key) else None

                ticket_info[endpoint] = {'table': table, 'index': index, 'fields': fields, 'unique_key': unique_key}
        return ticket_info

    def create_field_mapping(self, endpoint_info):
        fields_config = endpoint_info['fields'].split(', ')
        field_mapping = {field.split(':')[0]: None for field in fields_config}
        if endpoint_info['endpoint'] == 'sc_item_option':
            for field in field_mapping.keys():
                field_mapping[field] = 'item_option_new'
        return field_mapping

    def process_data(self, response, field_mapping):
        processed_data = []
        for record in response.get('result', []):
            filtered_record = {}
            for field, nested_key in field_mapping.items():
                if nested_key and nested_key in record and field in record[nested_key]:
                    filtered_record[field] = record[nested_key][field]
                else:
                    filtered_record[field] = record.get(field)
            processed_data.append(filtered_record)
        return processed_data

    def fetch_and_store_data(self, endpoint, sys_id=None):

        # Log the start of the data fetching and storing process for a given endpoint
        self.logger.info(f"Fetching and storing data for endpoint: {endpoint}")


        # Retrieve configuration information for the specified endpoint
       # print(self.ticket_info[endpoint])
        info = self.ticket_info[endpoint]
        field_mapping = self.create_field_mapping(info)
        groups = self.config.get('ServiceNow', 'groups')
        table = info['table']
        fields_key = f'servicenow_fields_{info["index"]}'
        fields_config = self.config.get('ServiceNow', fields_key).split(', ')
        fields = [field.split(':')[0] for field in fields_config]

        try:
            # Attempt to get the unique key for the ServiceNow table
            unique_key = self.config.get('ServiceNow', f'servicenow_unique_key_{info["index"]}')
        except Exception as e:
            # Log any errors encountered during fetching the unique key
            self.logger.error(f"Error fetching unique key: {e}")
            unique_key = None

        # Set up ServiceNow authentication credentials
        servicenow_auth = (self.config.get('ServiceNow', 'user'), self.config.get('ServiceNow', 'password'))
       
        if endpoint == "sc_item_option" and sys_id:
            query_fields = ','.join(fields)
            params = f'?sysparm_query=^!JOINsc_item_option.sys_id=sc_item_option_mtom.sc_item_option!^JOINsc_item_option_mtom.request_item=sc_req_item.sys_id!sys_id={sys_id}&sysparm_display_value=true&sysparm_fields=item_option_new,value'
            api_endpoint = f"{self.config.get('ServiceNow', 'instance')}/table/{endpoint}{params}"
            # Make the API call and store the response
            response = self.make_api_call(api_endpoint, params=params, auth=servicenow_auth)
            processed_data = self.process_data(response, field_mapping)
            print(processed_data)
        elif endpoint == "sys_audit" and sys_id:
            fields = [item.replace('"', '') for item in fields]
            audit_params = {
            'sysparm_query': f'tablename=sc_task^documentkey={sys_id}',
            'sysparm_fields': ','.join(fields)
            }
            audit_endpoint = f"{self.config.get('ServiceNow', 'instance')}/api/now/table/{endpoint}"
            response = self.make_api_call(audit_endpoint, params=audit_params, auth=servicenow_auth)
            
        elif endpoint == "sys_journal_field" and sys_id:
            journal_params = {
                        'sysparm_query': f'element_id={sys_id}&element=comments^ORelement=work_notes',
                        'sysparm_fields': ','.join(fields)
                    }
            journal_endpoint = f"{self.config.get('ServiceNow', 'instance')}/api/now/table/{endpoint}"
            response = self.make_api_call(journal_endpoint, params=journal_params, auth=servicenow_auth)

        elif endpoint == "sys_history_line" and sys_id:
            history_params = {
                            'sysparm_query': f'set.id={sys_id}',
                            'sysparm_fields': ','.join(fields)
                        }
            
            history_endpoint  = f"{self.config.get('ServiceNow', 'instance')}/api/now/table/{endpoint}/"
            response = self.make_api_call(history_endpoint, params=history_params, auth=servicenow_auth)

        else:
            # Build the API endpoint URL for the ServiceNow table
            api_endpoint = f"{self.config.get('ServiceNow', 'instance')}/api/now/table/{endpoint}"
            default_params = {'sysparm_query': f'assignment_group={groups}','sysparm_fields': ','.join(fields)}
          #  default_params = {'sysparm_fields': ','.join(fields)}
            response = self.make_api_call(api_endpoint, params=default_params, auth=servicenow_auth)

        if response and 'result' in response:
            for record in response['result']:
                # Prepare the record for insertion/upsert into the database
                filtered_record = {}
                for field, field_config in zip(fields, fields_config):
                    value = record.get(field, None)
                    if isinstance(value, dict) and 'value' in value:
                        filtered_record[field] = value['value']
                    elif "TIMESTAMP" in field_config:
                        filtered_record[field] = self.convert_to_standard_timestamp(value)
                    else:
                        filtered_record[field] = value

                try:
                    # Insert or update the record in the database
                    unique_keys = [unique_key] if unique_key else []
                    self.database.upsert_data(table, fields, filtered_record, unique_keys)
                except Exception as e:
                    # Log any errors encountered during the database upsert operation
                    self.logger.error(f"Error during upsert operation: {e}")
        if endpoint == "sc_req_item":
            # After fetching and storing sc_req_item, fetch and store related sc_item_option
            for item in response['result']:
                sys_id = item.get('sys_id')
                if sys_id:
                    self.fetch_and_store_data("sc_item_option",sys_id)
        if endpoint == "sc_task":
            for item in response['result']:
                sys_id = item.get('sys_id')
                if sys_id:
                    self.fetch_and_store_data("sys_audit",sys_id)
                    self.fetch_and_store_data("sys_journal_field",sys_id)
                    self.fetch_and_store_data("sys_history_line",sys_id)

    def convert_to_standard_timestamp(self, value):
        # Convert a timestamp value to a standard format, if not empty
        if value:
            try:
                return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                # Log any errors encountered during timestamp conversion
                self.logger.error(f"Timestamp conversion error: {e}")
                return None
        return None

