import configparser

class Config:
    def __init__(self, config_file):
        # Initialize the configuration parser
        self.config = configparser.ConfigParser()

        # Read the configuration from the specified file
        self.config.read(config_file)
    
    def get(self, section, key):
        # Retrieve a specific configuration value from a given section and key
        return self.config.get(section, key)
    
    def has_option(self, section, option):
        # Check if a specific option exists within a section
        return self.config.has_option(section, option)
    
    def options(self, section):
        # Get all the options available in a specific section
        return self.config.options(section)
    
    def getint(self, section, option):
            return int(self.get(section, option))