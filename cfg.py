# On different platforms
# Linux: need unixodbc (or equivalent) plus the SQL Server ODBC driver
# Windows: the driver manager is usually present, but users still need the SQL Server ODBC driver

import urllib.parse

package_name = 'SQL Server to PostgreSQL data migration tool'

active_threads = 3

chunk_size = 100000

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
	"database": "target",
    "user": "SuperUser", 
    "pwd": "Password123"
}
# ----------------------------------------


# don't mess with this unless you know what you're doing. The connection string is built from the above parameters.
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

enumerate_tables_query = '''
-- enumerate tables to migrate
;WITH t as (
	SELECT 
		'[' + s.name + '].[' + t.name + ']' as table_name
        , CASE s.name
            WHEN 'dbo' THEN 'public'
            ELSE s.name
          END 
          + '.' + t.name as pg_table_name
        , t.object_id
	FROM sys.tables as t
    INNER JOIN sys.schemas as s
        ON t.schema_id = s.schema_id
	WHERE t.type_desc = 'USER_TABLE'
)
, tbls as (
	SELECT t.table_name, t.pg_table_name, t.object_id, 0 as lvl
	FROM t
	WHERE NOT EXISTS (
		/*
			first level (lvl = 0):
			Only tables that are not children of FKs
			fk.parent_object_id is the object on which the FK is hung.
			It is actually the CHILD table of the foreign key
			relationship.
			fk.reference_object_id is the PARENT of the fk
			relationship
		*/
		SELECT 1
		FROM sys.foreign_keys as fk
		WHERE t.object_id = fk.parent_object_id
	)

	UNION ALL

	SELECT t.table_name, t.pg_table_name, t.object_id, tbls.lvl + 1 as lvl
	FROM t
	INNER JOIN sys.foreign_keys as fk
		ON t.object_id = fk.parent_object_id
	INNER JOIN tbls 
		ON fk.referenced_object_id = tbls.object_id
)
SELECT x.table_name, x.object_id, x.lvl
FROM (
	SELECT 
		*
		-- if a table is involved with more than one FK, just take the one with 
		-- the highest level and hope for the best.
		, ROW_NUMBER() OVER (PARTITION BY tbls.object_id ORDER BY lvl DESC) as rn 
	FROM tbls
) as x
WHERE x.rn = 1
ORDER BY x.lvl, x.table_name
'''

