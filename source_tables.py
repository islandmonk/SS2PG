import sqlalchemy
import pandas as pd
import cfg

c_log = cfg.log_to_the_log_file

the_script = """
    -- enumerate tables to migrate
    ;WITH t as (
        SELECT 
            '[' + s.name + '].[' + t.name + ']' as table_name
            , t.object_id
        FROM sys.tables as t
        INNER JOIN sys.schemas as s
            ON t.schema_id = s.schema_id
        WHERE t.type_desc = 'USER_TABLE'
    )
    , tbls as (
        SELECT t.table_name, t.object_id, 0 as lvl
        FROM t
        WHERE NOT EXISTS (
            /*
                first level (lvl = 0):
                Tables that are not children of FKs
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

        SELECT t.table_name, t.object_id, tbls.lvl + 1 as lvl
        FROM t
        INNER JOIN sys.foreign_keys as fk
            ON t.object_id = fk.parent_object_id
        INNER JOIN tbls 
            ON fk.referenced_object_id = tbls.object_id
    )
    SELECT 
          x.table_name
        , x.object_id
        , x.lvl
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
"""

def source_tables(source_engine: sqlalchemy.engine.base.Engine) -> pd.DataFrame:
    return pd.read_sql(the_script, source_engine)
