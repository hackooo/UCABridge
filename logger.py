import json
import datetime
import os
import inspect

class Logger:
    def __init__(self, log_folder='logs'):
        self.log_folder = log_folder
        if not os.path.exists(self.log_folder):
            os.makedirs(self.log_folder)

    def _get_service_name(self):
        """
        Get the name of the service (module) that is calling the logger.
        """
        stack = inspect.stack()
        for frame_info in stack:
            module = inspect.getmodule(frame_info.frame)
            if module and module.__name__ != __name__:
                return module.__name__.split('.')[-1]  # Get the last part of the module name
        return 'UnknownService'

    def log(self, message_type, message_content):
        service = self._get_service_name()
        log_file_path = os.path.join(self.log_folder, f"{service}.json")

        log_entry = {
            'service': service,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message_type': message_type,
            'message_content': message_content
        }

        with open(log_file_path, 'a') as file:
            file.write(json.dumps(log_entry) + '\n')

    def info(self, message):
        self.log('INFO', message)

    def error(self, message):
        self.log('ERROR', message)
