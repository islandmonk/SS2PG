from prompt_toolkit.shortcuts import ProgressBar, ProgressBarCounter
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts.progress_bar import formatters
import pandas as pd
import sqlalchemy as sa
import cfg
import table_create_script as tcs
import table_metadata as tm
import pg_table_exists as pte
import existing_target_columns as tc
from TableMetadata import TableMetadata

c_log = cfg.log_to_the_log_file

# Define style once globally
PROGRESS_STYLE = Style.from_dict({
    'label': 'bg:#000000 #ffff00',
    'percentage': 'bg:#ffcfb1 #000000',
    'current': '#448844',
    'bar': '',
    'bar-a': 'bg:#01754f #000000',  # Green completed section
    'bar-b': 'bg:#ffffff #000000',  # White progress bar head
    'bar-c': 'bg:#444444',           # Dark incomplete section
    'time-elapsed': '#888888',
    'time-left': '#ff8800',
})

custom_formatters = [
    formatters.Label(width=30, suffix=': '),  # Fixed 30-character width for labels
    formatters.Text(' '),
    formatters.Percentage(),
    formatters.Text(' '),
    formatters.Bar(sym_a='-', sym_b='<', sym_c='.'),
    formatters.Text('  '),
]

def push_to_pg(df, target_engine: sa.engine.base.Engine, tmd: TableMetadata):
    table = tmd.pg_name.split('.')[-1]  
    schema = tmd.pg_name.split('.')[0]  
    columns = ", ".join(df.columns)

    target_columns = tc.existing_target_columns(pg_name=tmd.pg_name, target_engine=target_engine)

    rows = []
    for row in df.itertuples(index=False, name=None):
        values = []
        for val, col in zip(row, df.columns):
            pg_type = str(target_columns.get(col))
            # c_log(f'col:{str(col)}', pg_type)

            if not pg_type:
                c_log(f"What should I do with this? {col} -> {pg_type}")

            if pd.isna(val):
                values.append(f"NULL::{pg_type}")

            elif isinstance(val, str) or pg_type == 'text':
                escaped = val.replace("'", "''")
                values.append(f"'{escaped}'::{pg_type}")

            elif pg_type == 'bit':
                if str(val).lower() == 'true':
                    values.append(f"1::{pg_type}")
                elif str(val).lower() == 'false':
                    values.append(f"0::{pg_type}")
                else:
                    values.append(f"'{val}'::{pg_type}")

            elif pg_type.__contains__('timestamp') :
                values.append(f"'{val}'::{pg_type}")

            else:
                values.append(f"{val}::{pg_type}")

        rows.append("(" + ", ".join(values) + ")")
    values_blob = ",\n    ".join(rows)

    the_big_insert_command = f"INSERT INTO {schema}.{table} ({columns}) \n VALUES \n    {values_blob};"
        
    #c_log(f"Pushing {len(df)} rows to {schema}.{table}")
    #c_log(f"{schema}.{table}", the_big_insert_command)
    #c_log("------------------------------------")

    try:
        with target_engine.connect() as conn:
            c_log(f"about to execute big INSERT {tmd.pg_name}", the_big_insert_command)
            result = conn.execute(sa.text(the_big_insert_command))
            conn.commit()
            c_log(f"{tmd.pg_name}: {result.rowcount} rows")

    except Exception as e:
            c_log(f"ERROR: the big insert failed {tmd.pg_name}", e)        

    finally: 
        conn.close()

    #raise RuntimeError("stop here")

def process_table(
    object_id: int, 
    source_engine: sa.engine.base.Engine, 
    target_engine: sa.engine.base.Engine
) -> tuple[str, bool, str]:

    """Process a single source table and write it to the target PostgreSQL engine."""
    tmd = TableMetadata(
        object_id=-1,
        sql_server_name="",
        pg_name="",
        pk_fields="",
        select_fields="",
        expected_row_count=0
    )

    pb = ProgressBar()

    try:
        tmd = tm.table_meta_data(object_id, source_engine) # TableMetadata object
        #c_log('tmd: ', tmd)

        # does the table exist in the PG target?
        with target_engine.connect() as conn:
            exists = pte.pg_table_exists(pg_name=tmd.pg_name, target_engine=target_engine)

        if exists:
            # The table exists. Right now, we know what we'd like the target columns types
            # should be. Right here, we need to see what they actually are. We're going to
            # do our best to push what we've got into those holes. This doesn't always work
            c_log(f'the table exists:  {tmd.pg_name}')
            #target_columns = tc.existing_target_columns(pg_name=pg_name, target_engine=target_engine)
            #c_log(f'target columns {tmd.pg_name}', str(target_columns))

        else:
            if cfg.create_pg_target_when_not_exists:
                c_log(f"Table {tmd.pg_name} does not exist in PostgreSQL. Create it.")

                create_table_script = tcs.get_create_table_script(object_id, source_engine)
                c_log(f"target {tmd.pg_name} creation script: ", create_table_script)


                if not create_table_script:
                    raise ValueError(f"Could not generate CREATE TABLE script for object_id = {tmd.object_id}")

                c_log(f"execute the script for {tmd.pg_name}")

                with target_engine.begin() as trgt_conn:
                    # gonna run a DO block here. These are smoother against a raw connection
                    raw_conn = trgt_conn.connection

                    try:
                        c_log("attempting to execute that command", create_table_script)
                        raw_conn.autocommit = True
                        cursor = raw_conn.cursor()
                        cursor.execute(create_table_script)

                    except Exception as e:
                        msg = f"Error executing CREATE TABLE script for  {tmd.pg_name}"
                        c_log(msg, e)
                        raise RuntimeError(f"{msg}: {e}")  

                # does it exist now?
                try:
                    exists = pte.pg_table_exists(pg_name=tmd.pg_name, target_engine=target_engine)  

                except Exception as e:
                    c_log(f"Failed to check table's existence {tmd.pg_name}", e)        
                    raise RuntimeError(f"Failed to check table's existence  {tmd.pg_name}: {e}")        

                if exists:
                    c_log(f"Successfully created table {tmd.pg_name} in PostgreSQL.")

                else:
                    c_log(f"Failed to create table {tmd.pg_name} in PostgreSQL.")
                    return tmd.sql_server_name, False, msg

            else:
                msg = f"Skipped {tmd.sql_server_name} -> {tmd.pg_name}: target does not exist and create_pg_target_when_not_exists is False."
                c_log(msg)
                return tmd.sql_server_name, False, msg

        c_log(f"Processing table {tmd.sql_server_name} (object_id = {tmd.object_id}) -> {tmd.pg_name}")

        # TRUNCATE the target table 
        with target_engine.begin() as trgt_conn:
            c_log(f"truncate {tmd.pg_name} ")
            truncate_command = f'TRUNCATE TABLE {tmd.pg_name}'
            trgt_conn.execute(sa.text(truncate_command))

        if cfg.I_am_testing:
            page_row_count = 5

        else:
            page_row_count = cfg.chunk_size

        if tmd.pk_fields:
            page_no = 0 # page_no is zero-based.
            total_rows_processed = 0

            with ProgressBar(style=PROGRESS_STYLE, formatters=custom_formatters) as pb:
                # The key: pb() wraps your iterable
                total_rows_expected = tmd.expected_row_count or 1
                counter : ProgressBarCounter = pb(
                    total=total_rows_expected, 
                    label=f"{tmd.sql_server_name}"
                )

                while True:
                    select_query = f"""
                        SELECT {tmd.select_fields}
                        FROM {tmd.sql_server_name} 
                        ORDER BY {tmd.pk_fields}
                        OFFSET {page_no * cfg.chunk_size} ROWS
                        FETCH NEXT {page_row_count} ROWS ONLY;
                    """

                    # c_log("select_query: ", select_query)

                    if page_no == 0:
                        c_log(f"-- page_no={page_no}", select_query )
                        pass
                    else:   
                        c_log(f'-- page_no={page_no}')
                        pass

                    try:
                        #with source_engine.connect() as conn:    
                        rows = pd.read_sql(select_query, source_engine)

                        if rows.empty:
                            c_log(f'no rows fetched {tmd.sql_server_name}. Nothing to push to PG ')
                            break
                        else:
                            rows.columns = [c.lower() for c in rows.columns]
                            c_log(f"Fetched {len(rows)} rows from {tmd.sql_server_name} -> {tmd.pg_name} (page {page_no})")
                            push_to_pg(rows, target_engine, tmd)

                            counter.items_completed += len(rows)
                            page_no += 1

                    except Exception as e:
                        c_log(f"ERROR: execution ", e)
                        
                return tmd.sql_server_name, True, select_query

        else:
            select_query = f"""
                SELECT {tmd.select_fields}
                FROM {tmd.sql_server_name} 
            """
            c_log(f'about to fetch {tmd.sql_server_name}. ', select_query)
            rows = pd.read_sql(sa.text(select_query), source_engine)

            if rows.empty:
                c_log(f'no rows fetched {tmd.sql_server_name}. Nothing to push to PG ')
            else:
                c_log(f"Fetched {len(rows)} rows from {tmd.sql_server_name}")
                rows.columns = [c.lower() for c in rows.columns]
                push_to_pg(rows, target_engine, tmd)
                
        return tmd.sql_server_name, True, select_query

    except Exception as exc:
        #c_log(f"ERROR: {tmd.sql_server_name} ")
        #c_log(f"ERROR: pk_fields: {tmd.pk_fields}  ")
        #c_log(f"ERROR: select_fields: {tmd.select_fields}")
        c_log(f"ERROR: {tmd.sql_server_name} ",  exc)
        return f"object_id = {tmd.object_id}", False, str(exc)
