import sqlalchemy
import pandas as pd

the_script = """
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
--AND t.name = 'file'
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
    SELECT x.table_name, x.object_id, x.lvl, COALESCE(ips.record_count, 0) as source_row_count
    FROM (
        SELECT 
            *
            -- if a table is involved with more than one FK, just take the one with 
            -- the highest level and hope for the best.
            , ROW_NUMBER() OVER (PARTITION BY tbls.object_id ORDER BY lvl DESC) as rn 
        FROM tbls
    ) as x
    OUTER APPLY (
        -- we desire a row count here. Expect large tables. Don't SELECT COUNT(*) against them.
        -- Giving preference to non-filtered indexes as a filtered index would yield a wrong row-count 
        -- (which would be fairly inconsequential, nothing will break if it's wrong)
        SELECT TOP 1 idx.index_id, type_desc, type
        FROM sys.indexes as idx
        WHERE x.[object_id] = idx.[object_id]
        ORDER BY idx.has_filter, idx.is_primary_key DESC
    ) as i
    LEFT OUTER JOIN sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, NULL) as ips
        ON x.[object_id] = ips.[object_id]
        AND i.[index_id] = ips.[index_id]
        AND ips.alloc_unit_type_desc = 'IN_ROW_DATA'
    WHERE x.rn = 1
    ORDER BY x.lvl, x.table_name
"""

def source_tables(source_engine: sqlalchemy.engine.base.Engine) -> pd.DataFrame:
    return pd.read_sql(the_script, source_engine)
