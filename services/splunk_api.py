from api_base import APIBase
from database import Database

class SplunkAPI(APIBase):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.database = Database(config, logger)
        self.splunk_info = self._extract_splunk_info()
        self.base_url = f"https://{config.get('Splunk', 'host')}:{config.get('Splunk', 'port')}"
        self.splunk_auth = (config.get('Splunk', 'username'), config.get('Splunk', 'password'))

    def _extract_splunk_info(self):
        splunk_info = {}
        for option in self.config.options('Splunk'):
            if option.startswith('splunk_table_'):
                index = option.split('_')[-1]
                table = self.config.get('Splunk', f'splunk_table_{index}')
                query = self.config.get('Splunk', f'splunk_query_{index}')
                try:
                    unique_key = self.config.get('Splunk', f'splunk_unique_key_{index}')
                except Exception as e:
                    self.logger.error(f"Error fetching unique key for Splunk table {table}: {e}")
                    unique_key = None
                splunk_info[table] = {'query': query, 'unique_key': unique_key, 'index': index}
        return splunk_info


    def execute_and_store_query(self, query_identifier):
        table, index = None, None
        for key, value in self.splunk_info.items():
            if f'splunk_query_{value["index"]}' == query_identifier:
                table = key
                index = value["index"]
                break

        if not table or not index:
            self.logger.error(f"No configuration found for query identifier: {query_identifier}")
            return

        info = self.splunk_info[table]
        query = info['query']
        unique_key = info['unique_key']

        # Splitting the query to extract the actual Splunk query
        _, spl_query = query.split(" | ", 1)

        search_url = f"{self.base_url}/services/search/jobs"
        params = {'search': spl_query, 'output_mode': 'json'}

        response = self.make_api_call(search_url, method='post', auth=self.splunk_auth, data=params)
        
        
        if response and 'sid' in response:
            # Extracting the search job ID from the response
            job_id = response['sid']

            # Constructing the URL to fetch the search results
            results_url = f"{self.base_url}/services/search/jobs/{job_id}/results"
            result_response = self.make_api_call(results_url, auth=self.splunk_auth, params={'output_mode': 'json'})
            
            if result_response and 'results' in result_response:
                # Iterating through the results and storing them in the database
                for result in result_response['results']:
                    # Preparing the unique keys for the upsert operation
                    unique_keys = [unique_key] if unique_key else []

                    # Insert or update the data in the database
                    self.database.upsert_data(index, result.keys(), result, unique_keys)
        else:
            self.logger.error(f"Error in Splunk API response: {response}")


