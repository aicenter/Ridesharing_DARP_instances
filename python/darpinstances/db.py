import atexit
import logging
from typing import List, Tuple, Iterable, Dict

import pandas as pd
import geopandas as gpd
import psycopg2
import psycopg2.errors
import sqlalchemy
import geoalchemy2
import sshtunnel
from psycopg2 import sql
from sqlalchemy.engine import Row
from sshtunnel import SSHTunnelForwarder

from .credentials_config import CREDENTIALS

DB_SCHEMA = 'public'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')


def connect_db_if_required(db_function):
    """
    Check and reset ssh connection decorator for methods working with the db
    """

    def wrapper(*args, **kwargs):
        db = args[0]
        db.start_or_restart_ssh_connection_if_needed()
        if not db.is_connected():
            db.set_up_db_connections()
        return db_function(*args, **kwargs)

    return wrapper


class __Database:
    """
    To be used as singleton instance db.

    Connection only happens when it is required.

    Import as:
    from db import db
    """
    SERVER = 'its.fel.cvut.cz'
    DBNAME = "opendata"
    HOST = "localhost"
    config = CREDENTIALS

    def __init__(self):
        # If private key specified, assume ssh connection and try to set it up
        self.db_server_port = self.config.db_server_port
        self.ssh_tunnel_local_port = 1113
        self.ssh_server = None

        self._psycopg2_connection = None
        self._sqlalchemy_engine = None

    def is_connected(self):
        return (self._psycopg2_connection is not None) and (self._sqlalchemy_engine is not None)

    def set_up_db_connections(self):
        # psycopg2 connection object
        logging.info("Starting _psycopg2 connection")
        self._psycopg2_connection = self.get_new_psycopg2_connnection()

        # SQLAlchemy init. SQLAlchemy is used by pandas and geopandas
        logging.info("Starting sql_alchemy connection")
        self._sql_alchemy_engine_str = self.get_sql_alchemy_engine_str()
        self._sqlalchemy_engine = sqlalchemy.create_engine(self._sql_alchemy_engine_str)

    def set_ssh_to_db_server_and_set_port(self):

        ssh_kwargs = dict(
            ssh_username=self.config.username,
            ssh_pkey=self.config.private_key_path,
            ssh_private_key_password=self.config.private_key_phrase,
            remote_bind_address=('localhost', self.db_server_port),
            local_bind_address=('localhost', self.ssh_tunnel_local_port)
            # skip_tunnel_checkup=False
        )
        try:
            self.ssh_server = sshtunnel.open_tunnel(self.SERVER, **ssh_kwargs)
        except sshtunnel.paramiko.SSHException as e:
            # sshtunnel dependency paramiko may attempt to use ssh-agent and crashes if it fails
            logging.warning(f"sshtunnel.paramiko.SSHException: '{e}'")
            self.ssh_server = sshtunnel.open_tunnel(self.SERVER, **ssh_kwargs, allow_agent=False)

        self.ssh_server.start()
        logging.info(
            "SSH tunnel established from %s to %s/%s",
            self.ssh_server.local_bind_address,
            self.ssh_server.ssh_host,
            self.db_server_port
        )

        self.db_server_port = self.ssh_server.local_bind_port

    def start_or_restart_ssh_connection_if_needed(self):
        """
        Set up or reset ssh tunnel.
        """
        if self.config.private_key_path is not None:
            if self.ssh_server is None:
                # INITIALIZATION
                logging.info("Connecting to ssh server")
                self.set_ssh_to_db_server_and_set_port()
            else:
                # RESET
                if not self.ssh_server.is_alive or not self.ssh_server.is_active:
                    self.ssh_server.restart()

    def get_sql_alchemy_engine_str(self):
        sql_alchemy_engine_str = 'postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}'.format(
            user=self.config.username,
            password=self.config.db_password,
            host=self.HOST,
            port=self.db_server_port,
            dbname=self.DBNAME)

        return sql_alchemy_engine_str

    def get_new_psycopg2_connnection(self):
        """
        Handles creation of db connection.

        TODO:
        For streamed connection, the sqlalchemy code was used for streamed reading into pandas:
        ENGINE = f'postgresql+psycopg2://{USERNAME}:{DB_PASSWORD}@{HOST}/{DBNAME}'
        READER = create_engine(ENGINE).connect().execution_options(stream_results=True)

        """
        try:
            psycopg2_connection = psycopg2.connect(
                user=self.config.username,
                password=self.config.db_password,
                host=self.HOST,
                port=self.db_server_port,
                dbname=self.DBNAME
            )

            atexit.register(psycopg2_connection.close)
            return psycopg2_connection
        except psycopg2.OperationalError as er:
            logging.error(str(er))
            logging.info("Tunnel status: %s", str(self.ssh_server.tunnel_is_up))
            return None

    @connect_db_if_required
    def execute_sql(self, query, *args) -> None:
        """
        Execute SQL that doesn't return any value.

        Psycopg is a postgres db connector for low-level connection to db.
        Requires cursors for executing sql, e.g.
        with db.PSYCOPG2_CONNECTION as con:
           with con.cursor() as curs:
               curs.execute(query)

        Note that leaving the connection context doesn't close the connection, instead,
        it commits the db transaction.
        Leaving the cursor context terminates the cursor and frees resources associated with it,
        such as memory holding query results or server-side stuff in case of server-side (named) cursors.

        See https://www.psycopg.org/docs/usage.html#transactions-control
        and https://www.psycopg.org/docs/cursor.html#cursor.execute
        """
        # with self._psycopg2_connection as con:
        #     with con.cursor() as curs:
        #         curs.execute(query, *args)
        self._sqlalchemy_engine.execute(query, *args)

    @connect_db_if_required
    def execute_sql_and_fetch_all_rows(self, query, *args) -> list[Row]:
        # with self._psycopg2_connection as con:
        #     with con.cursor() as curs:
        #         try:
        #             curs.execute(query, *args)
        #         except psycopg2.errors.SyntaxError as err:
        #             logging.error("Syntax error in the SQL statement:")
        #             logging.error(query)
        #             raise err
        #         result = curs.fetchall()
        result = self._sqlalchemy_engine.execute(query, *args).all()
        return result

    @connect_db_if_required
    def execute_count_query(self, query: str) -> int:
        data = self.execute_sql_and_fetch_all_rows(query)
        return data[0][0]

    @connect_db_if_required
    def drop_table_if_exists(self, table_name: str) -> None:
        drop_sql = sql.SQL("DROP TABLE IF EXISTS {table}").format(table=sql.Identifier(table_name))
        self.execute_sql(drop_sql)

    @connect_db_if_required
    def execute_query_to_pandas(self, sql: str, **kwargs) -> pd.DataFrame:
        """
        Execute sql and load the result to Pandas DataFrame

        kwargs are the same as for the pd.read_sql_query(), notably
        index_col=None
        """
        # with self._psycopg2_connection as con:
        data = pd.read_sql_query(sql, self._sqlalchemy_engine, **kwargs)
        return data

    @connect_db_if_required
    def execute_query_to_geopandas(self, sql: str, **kwargs) -> pd.DataFrame:
        """
        Execute sql and load the result to Pandas DataFrame

        kwargs are the same as for the pd.read_sql_query(), notably
        index_col=None
        """
        # with self._psycopg2_connection as con:
        data = gpd.read_postgis(sql, self._sqlalchemy_engine, **kwargs)
        return data

    @connect_db_if_required
    def dataframe_to_db_table(self, df: pd.DataFrame, table_name: str, **kwargs) -> None:
        """
        Save DataFrame to a new table in the database

        the dataframe method cannot accept psycopg2 connection, only SQLAlchemy
        connections or connection strings.

        https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_sql.html
        """
        df.to_sql(table_name, con=self._sqlalchemy_engine, if_exists='append', index=False)

    @connect_db_if_required
    def db_table_to_pandas(self, table_name: str, **kwargs) -> pd.DataFrame:
        return pd.read_sql_table(table_name, con=self._sqlalchemy_engine, **kwargs)


# db singleton
db = __Database()


class DBTable:
    """Baseclass representing a database table"""
    db = db

    def __init__(self, table_name: str):
        self.table_name = table_name

    def to_df(self, **kwargs) -> pd.DataFrame:
        return self.db.db_table_to_pandas(self.table_name, **kwargs)

    def exists(self) -> None:
        exists_query = f"""
        SELECT EXISTS (SELECT 1 FROM information_schema.tables 
        WHERE table_schema = '{DB_SCHEMA}' AND table_name = '{self.table_name}')
        """
        return self.db.execute_query_to_pandas(exists_query).iloc[0, 0]

    def drop_if_exists(self) -> None:
        self.db.drop_table_if_exists(self.table_name)

    def get_columns_to_df(self,
                          columns: Iterable[str] = (),
                          column_as: Dict[str, str] = dict(),
                          join_sql: str = "",
                          limit: int = None, **kwargs) -> pd.DataFrame:
        """
        Return origin, result columns of odt table + selected columns renamed according to the mapping.

        :param join_sql: join sql
        :param column_as: dict, keys are new names in the returned dataframe, values are columns in the table. Can be empty.
        :param columns: columns from table that will not be renamed
        :param limit: limit number of rows from the table, default = None (no limit)
        :return: dataframe of selected columns
        """
        db_cols = ",".join([f"{db_col} AS {result_field}" for result_field, db_col in column_as.items()])
        original_cols = ", ".join(columns)
        # filter removes empty strings
        query = f"SELECT {', '.join(filter(None, [original_cols, db_cols]))} FROM {self.table_name} "
        query += f"\n{join_sql}"
        if limit is not None:
            query += f"\nLIMIT {limit}"
        return self.db.execute_query_to_pandas(query, **kwargs)
