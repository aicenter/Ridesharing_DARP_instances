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

        database = config["database"]

        self.db_server_port = int(database.get("db_server_port", "5432"))
        self.username = database.get("username", None)
        self.db_password = database.get("db_password", "")
        self.db_host = database.get("db_host", "localhost")
        self.db_name = database.get("db_name", None)

        ssh = config['ssh']
        self.server_username = ssh.get("server_username", None)
        self.private_key_path = ssh.get("private_key_path", None)
        self.private_key_phrase = ssh.get("private_key_passphrase", None)
        self.host = ssh.get("host", "localhost")
        self.server = ssh.get("server", None)

        if "username" not in database or "db_name" not in database:
            raise RuntimeError(
                'Database critical credentials ("username" or/and "db_name") not found in config file. Parsed credentials are:\n{}'.format(
                    self
                )
            )


CREDENTIALS = CredentialsConfig()
