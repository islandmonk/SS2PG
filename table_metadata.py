import sqlalchemy

the_script = """
    SELECT 
            '[' + s.[name] + '].[' + t.[name] + ']' as sql_server_table_name 
        , CASE s.[name]
            WHEN 'dbo' THEN 'public'
            ELSE s.[name]
            END 
        + '.' + t.[name] as pg_table_name
        , pk.pk_columns
        , sc.select_columns
    FROM sys.tables as t
    INNER JOIN sys.schemas as s
        ON t.schema_id = s.schema_id   
    OUTER APPLY (
        SELECT STRING_AGG('[' + c.name + ']', ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) as pk_columns
        FROM sys.indexes as i
        INNER JOIN sys.index_columns as ic
            ON i.object_id = ic.object_id
            AND i.index_id = ic.index_id
        INNER JOIN sys.columns as c
            ON ic.object_id = c.object_id
            AND ic.column_id = c.column_id
        WHERE i.is_primary_key = 1
        AND i.object_id = t.object_id
    ) as pk -- primary key columns
    OUTER APPLY (
        SELECT STRING_AGG('[' + c.name + ']', ', ') WITHIN GROUP (ORDER BY c.column_id) as select_columns
        FROM sys.columns as c 
        WHERE c.object_id = t.object_id
        AND c.is_computed = 0
    ) as sc -- columns to be selected     
    WHERE t.object_id = :oid
"""

def table_meta_data (object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> tuple[str, str, str, str]:
    with source_engine.connect() as conn:
        select_query = the_script
        result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
        row = result.fetchone()

        if not row:
            raise ValueError(f"Could not resolve names for object_id={object_id}")

        sql_server_name, pg_name, pk_fields, select_fields = row[0], row[1], row[2], row[3]

    return sql_server_name, pg_name, pk_fields, select_fields
