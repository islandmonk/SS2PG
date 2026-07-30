import sqlalchemy
import cfg
from TableMetadata import TableMetadata

c_log = cfg.log_to_the_log_file

the_script = """
    SELECT 
          t.[object_id]
        , '[' + s.[name] + '].[' + t.[name] + ']' as sql_server_table_name 
        , CASE s.[name]
            WHEN 'dbo' THEN 'public'
            ELSE s.[name]
            END 
        + '.' + t.[name] as pg_table_name
        , pk.pk_columns
        , sc.select_columns
        , COALESCE(ips.record_count, 0) as record_count
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
    OUTER APPLY (
        -- It would be nice to have a row count here. Anticipate large tables. Don't SELECT COUNT(*) against them.
        -- Giving preference to non-filtered indexes as a filtered index would yield a wrong row-count 
        -- (which would be fairly inconsequential, nothing will break if it's wrong)
        SELECT TOP 1 idx.index_id, type_desc, type
        FROM sys.indexes as idx
        WHERE t.[object_id] = idx.[object_id]
        ORDER BY idx.has_filter, idx.is_primary_key DESC
    ) as i
    OUTER APPLY (
        SELECT SUM(ps.row_count) as record_count
        FROM sys.dm_db_partition_stats ps
        WHERE ps.object_id = t.[object_id]
            AND ps.index_id = i.index_id
    ) as ips
    WHERE t.object_id = :oid
"""

def table_meta_data (object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> TableMetadata:
    c_log(f"object_id: {object_id}" )
    
    try:
        with source_engine.connect() as conn:
            select_query = the_script
            result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
            row = result.fetchone()

            if not row:
                raise ValueError(f"Could not resolve names for object_id={object_id}")

    except Exception as e:
        c_log(f"Failed to get table's metadata {object_id}", e)        
        raise RuntimeError(f"Failed to get table's metadata  {object_id}: {e}")        

    return TableMetadata(
        object_id=int(row[0]),
        sql_server_name=row[1],
        pg_name=row[2],
        pk_fields=row[3],
        select_fields=row[4],
        expected_row_count=int(row[5])
    )