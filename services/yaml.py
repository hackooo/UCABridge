import os
from database import Database
import yaml
import uuid

class Yaml():
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        # Initialize the Database object for data operations
        self.database = Database(config, logger)

        # Extract information about Yaml
        self.yaml_info = self._extract_yaml_info()

        # Log that the Yaml Job has been initialized
        self.logger.info("Yaml Job")

    def _extract_yaml_info(self):
        self.logger.info("Extracting YAML information")
        yaml_info = {}
        for option in self.config.options('Yaml'):
            if option.startswith('yaml_table_'):
                index = option.split('_')[-1]
                table = self.config.get('Yaml', f'yaml_table_{index}')
                schema = self.config.get('Yaml', f'yaml_schema_{index}')
                schema = {k.strip(): v.strip() for k, v in (pair.split(':') for pair in schema.split(', ') if len(pair.split(':')) == 2)}
#                schema = {k.strip(): v.strip() for k, v in (item.split(' = ') for item in self.config.get('Yaml', f'yaml_schema_{index}').split(', '))}
                # Handling the absence of certain configuration values
                fields_key = f'yaml_fields_{index}'
                unique_key_key = f'yaml_unique_key_{index}'
                fields = self.config.get('Yaml', fields_key) if self.config.has_option('Yaml', fields_key) else None
                unique_key = self.config.get('Yaml', unique_key_key) if self.config.has_option('Yaml', unique_key_key) else None

                yaml_info[table] = {'table': table, 'index': index, 'fields': fields, 'unique_key': unique_key, 'schema': schema}
        return yaml_info
    

    def generate_yaml_files(self):
        
        for index, info in self.yaml_info.items():
            table = info['table']
            fields_key = f'yaml_fields_{info["index"]}'
            fields_config = self.config.get('Yaml', fields_key).split(', ')
            fields = [field.split(':')[0] for field in fields_config]

            # Fetch data from the table
            results = self.database.view_data(table, fields)


            for row in results:
                # Convert the row to a dictionary
                row_dict = dict(zip(fields, row))

                # Handle the 'uc_id' field
                id = row_dict.get('uc_id')
                print(row_dict)
                if not id:
                    id = str(uuid.uuid4())
                    self.logger.warning(f"uc_id not found for a row in {table}, generating UUID: {id}")

                # Transform data based on the schema
                formatted_row_data = transform_data(row_dict, info['schema'])

                os.makedirs('yamls', exist_ok=True)

                # Write to a YAML file named after the uc_id value
                folder_name = table.split("_")[1] if "_" in table else ""
                
                os.makedirs(f"yamls/{folder_name}", exist_ok=True)

                file_path = os.path.join(f"yamls/{folder_name}", f"{id}.yaml")
                with open(file_path, 'w') as file:
                    yaml.dump([formatted_row_data], file, default_flow_style=False, sort_keys=False, indent=2)

                self.logger.info(f"YAML file {file_path} generated for {table}.")



    def generate_html_forms(self):
        for index, info in self.yaml_info.items():
            fields = info['fields'].split(', ') if info['fields'] else []
            html_content = "<!DOCTYPE html>\n<html lang='en'>\n<head>\n    <meta charset='UTF-8'>\n    <title>Form</title>\n</head>\n<body>\n<form action='' method='post'>\n"
            
            for field in fields:
                field_name = field.split(':')[0]
                html_content += f"    <label for='{field_name}'>{field_name}:</label>\n    <input type='text' id='{field_name}' name='{field_name}'><br><br>\n"
            
            html_content += "    <input type='submit' value='Submit'>\n</form>\n</body>\n</html>"

            with open(f"{info['table']}.html", 'w') as file:
                file.write(html_content)
            self.logger.info(f"HTML form for {info['table']} generated.")



def transform_data(row, schema):
    yaml_data = {}
    
    for key, value in schema.items():
        keys = value.split('.')
        current_level = yaml_data
        for k in keys[:-1]:
            if k not in current_level:
                current_level[k] = {}
            current_level = current_level[k]

        # Check if the key exists in the row data
        if keys[-1] in row:
            # Special handling for lists and nested objects
            if isinstance(row[keys[-1]], str) and ',' in row[keys[-1]]:
                current_level[keys[-1]] = [item.strip() for item in row[keys[-1]].split(',')]
            else:
                current_level[keys[-1]] = row[keys[-1]]
        else:
            # Handle missing key (e.g., set to None or a default value)
            current_level[keys[-1]] = None  # or some default value

    return yaml_data
