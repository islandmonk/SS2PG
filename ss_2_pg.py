from prompt_toolkit.shortcuts import ProgressBar
from prompt_toolkit.formatted_text import FormattedText
import concurrent.futures
import pandas as pd
import pyodbc
import sqlalchemy
import time
import cfg
import table_create_script

def source_tables(source_engine: sqlalchemy.engine.base.Engine) -> pd.DataFrame:
    return pd.read_sql(cfg.enumerate_tables_query, source_engine)

def pk_cols(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> str:
    """Return a single comma-separated string of PK columns (with brackets), or empty string."""
    with source_engine.connect() as conn:
        select_query = """
            SELECT STRING_AGG('[' + c.name + ']', ', ') WITHIN GROUP (ORDER BY ic.key_ordinal)
            FROM sys.indexes as i
            INNER JOIN sys.index_columns as ic
                ON i.object_id = ic.object_id
                AND i.index_id = ic.index_id
            INNER JOIN sys.columns as c
                ON ic.object_id = c.object_id
                AND ic.column_id = c.column_id
            WHERE i.is_primary_key = 1
              AND i.object_id = :oid
        """
        # sqlalchemy syntax for parameterized queries uses :param_name, not ? as in pyodbc.  
        # See https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Connection.execute
        
        result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
        the_pk_names = result.scalar_one_or_none()
    return the_pk_names or ""


def select_cols(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> str:
    """Return a single comma-separated string of non-calculated columns (with brackets)."""
    with source_engine.connect() as conn:
        select_query = """
            SELECT STRING_AGG('[' + c.name + ']', ', ') WITHIN GROUP (ORDER BY c.column_id)
            FROM sys.columns as c 
            WHERE c.object_id = :oid
            AND c.is_computed = 0
        """

        result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
        the_column_names = result.scalar_one_or_none()
    
    return the_column_names if the_column_names is not None else ""


def table_names(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> tuple[str, str]:
    """Return the SQL Server table name and expected PG table name"""

    with source_engine.connect() as conn:
        select_query = """
            SELECT 
                  '[' + s.[name] + '].[' + t.[name] + ']' as sql_server_table_name 
                , CASE s.[name]
                    WHEN 'dbo' THEN 'public'
                    ELSE s.[name]
                  END 
                + '.' + t.[name] as pg_table_name
            FROM sys.tables as t
            INNER JOIN sys.schemas as s
                ON t.schema_id = s.schema_id        
            WHERE t.object_id = :oid
        """
        result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
        row = result.fetchone()

        if not row:
            raise ValueError(f"Could not resolve names for object_id={object_id}")

        sql_server_name, pg_name = row[0], row[1]

    return sql_server_name, pg_name

def pg_table_create_script(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> str:
    """
        Return a script that will create a similar table in PG. This is a best-effort attempt, and may not be perfect. 
        It will only create the source tale's primary key if it has one. There is no context in PG where clustering.
        All textual datatypes will be created as TEXT, and all numeric datatypes will be created as NUMERIC. This is a best-effort attempt, and may not be 
        perfect. It will only create the source table's primary key if it has one. There is no context in PG where 
        clustering is important. No attention will be paid to how the source table is clustered.
    """

    with source_engine.connect() as conn:
        select_query = """
            SELECT 
                  '[' + s.[name] + '].[' + t.[name] + ']' as sql_server_table_name 
                , CASE s.[name]
                    WHEN 'dbo' THEN 'public'
                    ELSE s.[name]
                  END 
                + '.' + t.[name] as pg_table_name
            FROM sys.tables as t
            INNER JOIN sys.schemas as s
                ON t.schema_id = s.schema_id        
            WHERE t.object_id = :oid
        """
        result = conn.execute(sqlalchemy.text(select_query), {"oid": object_id})
        row = result.fetchone()

        if not row:
            raise ValueError(f"Could not resolve names for object_id={object_id}")

        sql_server_name, pg_name = row[0], row[1]

    return sql_server_name, pg_name
    

def push_to_pg(df, target_engine: sqlalchemy.engine.base.Engine, table_name: str):
    # this might not warrant a separate function, but it gives us a place to add
    # logging or other functionality later if we want to.
    df.to_sql(table_name, con=target_engine, if_exists='append', index=False)

def process_table(object_id: int, source_engine: sqlalchemy.engine.base.Engine, target_engine: sqlalchemy.engine.base.Engine) -> tuple[str, bool, str]:
    # pull the source data and push to PG page by page if we have a primary key, otherwise do a full select and push.
    try:
        table_name, pg_name = table_names(object_id, source_engine)

        print(f"Processing table {table_name} (object_id={object_id}) -> {pg_name}")

        pk_fields = pk_cols(object_id, source_engine)
        select_fields = select_cols(object_id, source_engine)

        if pk_fields:
            # we have a primary key, so we can do a paged select

            page_no = 0

            while True:
                select_query = f"""
                    SELECT {select_fields} 
                    FROM {table_name} 
                    ORDER BY {pk_fields}
                    OFFSET {page_no * cfg.chunk_size} ROWS -- page_no is zero-based.
                    FETCH NEXT {cfg.chunk_size} ROWS ONLY;
                """

                rows = pd.read_sql(select_query, source_engine)

                if not rows.empty:
                    # assume PG table has column names in lower case
                    rows.columns = [c.lower() for c in rows.columns]
                else:
                    break

                # push the rows to their target table in PostgreSQL
                push_to_pg(rows, target_engine, pg_name)
                print(f"Fetched {len(rows)} rows from {table_name} -> {pg_name} (page {page_no})")

                page_no += 1

            return table_name, True, select_query

        else:
            # no primary key, so we have to do a full select
            select_query = f"""
                SELECT {select_fields} 
                FROM {table_name} 
            """
            rows = pd.read_sql(select_query, source_engine)
            total = len(rows)
            return table_name, True, select_query

    except Exception as exc:
        print(f"table_name: {table_name} pk_fields: {pk_fields} select_fields: {select_fields} ")
        print(f"Error processing table with {select_query}: {exc}")
        return f"object_id={object_id}", False, str(exc)


def main():
    source_engine = sqlalchemy.create_engine(
        cfg.sql_server_connection_string,
        pool_size = cfg.active_threads,
        max_overflow = 2,
        pool_pre_ping = True,
    )

    target_engine = sqlalchemy.create_engine(
        cfg.postgres_connection_string,
        pool_size = cfg.active_threads,
        max_overflow = 2,
        pool_pre_ping = True, 
        # pre_ping sends a SELECT 1 query to the server to check if the connection is alive. 
        # if you're seeing a lot of this in your profiler or extended events sessions, that's 
        # what this is. It is safe to ignore, but if you want to reduce the noise, you can 
        # remove this parameter.
    )

    ss_tables = source_tables(source_engine)
    print(ss_tables.head())

    # process tables level-by-level (lvl=0 first)
    lvls = sorted(ss_tables['lvl'].unique())

    for lvl in lvls:
        rows = ss_tables[ss_tables['lvl'] == lvl]
        tables = rows['table_name'].tolist()
        object_ids = rows['object_id'].tolist() 

        print(f"Processing level {lvl} -- {len(tables)} tables (workers={cfg.active_threads})")

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.active_threads) as exe:
            future_to_table = {exe.submit(process_table, o, source_engine, target_engine): o for o in object_ids}
            for fut in concurrent.futures.as_completed(future_to_table):
                table = future_to_table[fut]
                try:
                    tbl, ok, msg = fut.result()

                except Exception as exc:
                    ok = False
                    msg = str(exc)
                    tbl = table
                status = "OK" if ok else "FAILED"
                print(f"{status}: {tbl} -- {msg}")
                results.append((tbl, ok, msg))

        # Small pause between levels because it feels right.
        # This isn't necessary at all, but it gives the user a 
        # chance to see the output of the previous level before the next level starts.
        time.sleep(0.1)

    print(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
