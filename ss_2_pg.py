'''
    Doug@HillsBrother.com
'''
import concurrent.futures
import pandas as pd
import pyodbc
import sqlalchemy
import time
import cfg
import source_tables as st
import process_table as pt
import threading

c_log = cfg.log_to_the_log_file

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
        # pool_pre_ping sends a SELECT 1 query to the server to check if the connection is alive. 
        # if you're seeing a lot of this in your profiler or extended events sessions, this's 
        # what that is. It is safe to ignore, but if you want to reduce the chatter, 
        # you can remove/falsify this parameter.
    )

    ss_tables = st.source_tables(source_engine)
    # print(ss_tables.head())

    # process tables level-by-level (lvl=0 first)
    lvls = sorted(ss_tables['lvl'].unique())

    for lvl in lvls:
        rows = ss_tables[ss_tables['lvl'] == lvl]
        tables = rows['table_name'].tolist()
        object_ids = rows['object_id'].tolist() 

        message = f"Processing level {lvl} -- {len(tables)} tables (workers={cfg.active_threads})"
        c_log(message)

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.active_threads) as exe:
            future_to_table = {
                exe.submit(pt.process_table, o, source_engine, target_engine): o for o in object_ids
            }
            
            for fut in concurrent.futures.as_completed(future_to_table):
                table = future_to_table[fut]
                try:
                    tbl, ok, msg = fut.result()

                except Exception as exc:
                    ok = False
                    msg = str(exc)
                    tbl = table
                    
                status = "OK" if ok else "FAILED"
                c_log(f"{status}: {tbl} -- {msg}")
                results.append((tbl, ok, msg))

        # Small pause between levels because it feels right.
        # This isn't necessary at all, but it gives the user a 
        # chance to see the output of the previous level before the next level starts.
        time.sleep(0.1)

    #print(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
