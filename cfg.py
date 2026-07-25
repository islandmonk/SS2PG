# On different platforms
# Linux: need unixodbc (or equivalent) plus the SQL Server ODBC driver
# Windows: the driver manager is usually present, but users still need the SQL Server ODBC driver
# Doug@HillsBrother.com

import urllib.parse
from datetime import datetime
import inspect

package_name = 'SQL Server to PostgreSQL data migration tool'

active_threads = 1

# If True, and the target table doesn't exist, the script will attempt to create the target table in PG.
# If the schema doesn't exist, it will also be created. This might not be desired behavior.
create_pg_target_when_not_exists = True

# when I'm paging a table, how many rows per page?
chunk_size = 10000

I_am_logging = True
I_am_testing = True # True keeps the data volumes lower

# this script generates huge insert commands. Sometimes you want to see
# the whole thing. Usually you don't
yes_log_the_whole_huge_command = False

truncated_command_length = 1000

log_file = 'logs/paging_queries.txt'

clear_log_file_at_start = True

#sql server connection
sql_server = {
    "database": "custodian",
    "driver": "ODBC Driver 18 for SQL Server",
    "server": '192.168.1.11',
    "user": "SuperUser",
    "pwd": "Password123",
    # set to 'yes' to allow connecting to servers with self-signed certs
    # in trusted/internal networks. For production, prefer a proper CA.
    "trust_server_certificate": "yes"
}

# PostgreSQL connection
postgres = {
    "host": "192.168.1.42",
    "port": "5432", 
	"database": "dtctest",
    "user": "postgres", 
    "pwd": "postgres"
}
# ----------------------------------------
# end of configuration section


# Be careful. The connection strings are built from the above parameters.
sql_server_connection_string = (
    'mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver={driver}&TrustServerCertificate={trust_server_certificate}'.format(
        user=sql_server['user'],
        pwd=sql_server['pwd'],
        server=sql_server['server'],
        database=sql_server['database'],
        driver=urllib.parse.quote_plus(sql_server['driver']),
        trust_server_certificate=sql_server['trust_server_certificate'],
    )
)

postgres_connection_string = (
    f'postgresql+psycopg://{postgres["user"]}:{postgres["pwd"]}@{postgres["host"]}:{postgres["port"]}/{postgres["database"]}'
)

def empty_the_log_file():
    with open(log_file, "w", encoding="utf-8") as f:
        pass

def log_to_the_log_file (subject: str, body: any = ""):
    body_text = str(body)
    if I_am_testing or I_am_logging:
        # Get the calling module name
        caller_frame = inspect.currentframe().f_back
        caller_module = inspect.getmodule(caller_frame).__name__
        caller_lineno = caller_frame.f_lineno
        
        if body:
            if yes_log_the_whole_huge_command or len(body) <= truncated_command_length:
                body_text = body
            else:
                remaining_length = len(body) - truncated_command_length
                body_text = body[:truncated_command_length] + " . . . + [" + str(remaining_length) + "]"

        first_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{caller_module}:{caller_lineno}] " + subject

        with open(log_file, 'a', encoding="utf-8") as f:
            f.write(first_line + '\n')
            if body_text:
                f.write(body_text + '\n')
                f.write("---------------------------------------------\n")