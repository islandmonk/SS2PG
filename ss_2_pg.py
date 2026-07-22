'''
    Doug@HillsBrother.com
'''
from prompt_toolkit.shortcuts import ProgressBar
from prompt_toolkit.formatted_text import FormattedText
import concurrent.futures
import pandas as pd
import pyodbc
import sqlalchemy
import time
import cfg
import table_create_script as tcs
import table_metadata as tm 
import source_tables as st

def push_to_pg(df, target_engine: sqlalchemy.engine.base.Engine, table_name: str):
    # this might not warrant a separate function, but it gives us a place to add
    # logging or other functionality later if we want to.
    df.to_sql(table_name, con=target_engine, if_exists='append', index=False)

def process_table(object_id: int, source_engine: sqlalchemy.engine.base.Engine, target_engine: sqlalchemy.engine.base.Engine) -> tuple[str, bool, str]:
    # pull the source data and push to PG page by page if we have a primary key, otherwise do a full select and push.
    table_name = None
    pg_name = None
    pk_fields = None
    select_fields = None
    select_query = None

    try:
        table_name, pg_name, pk_fields, select_fields = tm.table_meta_data(object_id, source_engine)

        # does the table exist in the PG target?
        with target_engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_schema = split_part(:pg_name, '.', 1)
                    AND table_name = split_part(:pg_name, '.', 2)
                )
            """), {"pg_name": pg_name})
            exists = result.scalar_one_or_none()        

        if not exists:
            if cfg.create_pg_tables:
                # create the table in PG
                create_table_script = tcs.get_create_table_script(object_id, source_engine)

                if not create_table_script:
                    raise ValueError(f"Could not generate CREATE TABLE script for object_id={object_id}")

                with target_engine.connect() as conn:
                    conn.execute(sqlalchemy.text(create_table_script))
                print(f"Created table {pg_name} in PostgreSQL.")
            else:
                msg = f"Skipped {table_name} -> {pg_name}: target does not exist and create_pg_tables is False."
                print(msg)
                return table_name, False, msg


        print(f"Processing table {table_name} (object_id={object_id}) -> {pg_name}")

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
        print(
            f"table_name: {table_name!r} pk_fields: {pk_fields!r} select_fields: {select_fields!r} "
        )
        print(f"Error processing table with {select_query!r}: {exc}")
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
        # if you're seeing a lot of this in your profiler or extended events sessions, this's 
        # what that is. It is safe to ignore, but if you want to reduce the chatter, 
        # you can remove this parameter.
    )

    ss_tables = st.source_tables(source_engine)
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
