import os
import pathlib
import configparser


def read_config(config_paths):
    """
    Read database credentials from .ini file.
    """
    config = configparser.ConfigParser()

    read_configs = config.read(config_paths)
    if read_configs:
        print("Successfully read db config from: {}".format(str(read_configs)))
    else:
        print("Failed to find any config in {}".format([os.path.abspath(path) for path in config_paths]))
    return config


class CredentialsConfig:
    CONFIG_PATHS = [f'{pathlib.Path(__file__).parent.parent.parent}/config.ini']

    def __init__(self):
        config = read_config(self.CONFIG_PATHS)
        self.private_key_path = config['ssh'].get('private_key_path', None)
        self.private_key_phrase = config['ssh'].get('private_key_passphrase', None)

        self.db_server_port = int(config['database'].get('db_server_port', "5432"))
        self.username = config['database']['username']
        self.db_password = config['database']['db_password']


CREDENTIALS = CredentialsConfig()
