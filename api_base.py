import os
import requests

class APIBase:
    def __init__(self, config, logger):
        # Store the configuration and logger instances
        self.config = config
        self.logger = logger

        # Set up any required proxy settings for network requests
        self._set_proxy()

    def _set_proxy(self):
        # Check if proxy usage is enabled in the configuration
        if self.config.get('Proxy', 'use_proxy').lower() == 'true':
            # Retrieve proxy settings from the configuration
            http_proxy = self.config.get('Proxy', 'http_proxy', fallback=None)
            https_proxy = self.config.get('Proxy', 'https_proxy', fallback=None)

            # Set the environment variables for HTTP and HTTPS proxies
            if http_proxy:
                os.environ['HTTP_PROXY'] = http_proxy
            if https_proxy:
                os.environ['HTTPS_PROXY'] = https_proxy

    def make_api_call(self, endpoint, method='get', params=None, data=None, auth=None):
        # Make an API call to the specified endpoint
        try:
            # Choose the HTTP method (GET or POST) for the request
            if method.lower() == 'post':
                response = requests.post(endpoint, params=params, data=data, auth=auth)
            else:
                response = requests.get(endpoint, params=params, auth=auth)

            # Raise an exception for HTTP error responses (e.g., 404, 500)
            response.raise_for_status()

            # Return the JSON response from the API call
            return response.json()
        except requests.RequestException as e:
            # Log the exception details if the API call fails
            self.logger.error(f"Error en la llamada API: {e}")

            # Return None to indicate failure
            return None
