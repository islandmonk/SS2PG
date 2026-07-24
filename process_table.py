import pandas as pd
import sqlalchemy as sa
import cfg
import table_create_script as tcs
import table_metadata as tm

c_log = cfg.log_to_the_log_file

def push_to_pg(df, target_engine: sa.engine.base.Engine, two_part_table_name: str):
    table = two_part_table_name.split('.')[-1]  
    schema = two_part_table_name.split('.')[0]  
    columns = ", ".join(df.columns)

    target_columns = existing_target_columns(pg_name=pg_name, target_engine=target_engine)
    print (target_columns)

    rows = []
    for row in df.itertuples(index=False, name=None):
        values = []
        for val, col in zip(row, df.columns):
            pg_type = str(target_columns.get(df[col].dtype))

            if not pg_type:
                c_log(f"What should I do with this dtype? {dtype} -> {pg_type}")

            if pd.isna(val):
                values.append(f"NULL::{pg_type}")

            elif isinstance(val, str) or pg_type == 'text':
                escaped = val.replace("'", "''")
                values.append(f"'{escaped}'::{pg_type}")

            elif pg_type == 'timestamp':
                values.append(f"'{val}'::{pg_type}")

            else:
                values.append(f"{val}::{pg_type}")

        rows.append("(" + ", ".join(values) + ")")
    values_blob = ",\n    ".join(rows)

    the_big_insert_command = f"INSERT INTO {schema}.{table} ({columns}) \n VALUES \n    {values_blob};"
        
    c_log(f"Pushing {len(df)} rows to {schema}.{table}")
    c_log(f"{schema}.{table}", the_big_insert_command)
    c_log("------------------------------------")

    with target_engine.begin() as conn:
        result = conn.execute(sa.text(the_big_insert_command))
        c_log(f"{schema}.{table}: {result.rowcount} rows")

    #raise RuntimeError("stop here")

def existing_target_columns(
    pg_name: str, 
    target_engine: sa.engine.base.Engine
) -> dict[str, str]:

    column_enumeration_text = f"""
        SELECT c.column_name, c.data_type 
        FROM information_schema.columns as c
        WHERE table_schema = split_part('{pg_name}', '.', 1)
        AND table_name = split_part('{pg_name}', '.', 2)
    """

    try:
        with target_engine.connect() as conn:
            result = conn.execute(sa.text(column_enumeration_text))
            rows = result.fetchall()

            # populate the dictionary
            return {row[0]: row[1] for row in rows}

    except Exception as e:
        raise RuntimeError(f"Failed to get columns for {pg_name}: {e}")        

def process_table(
    object_id: int, 
    source_engine: sa.engine.base.Engine, 
    target_engine: sa.engine.base.Engine
) -> tuple[str, bool, str]:

    """Process a single source table and write it to the target PostgreSQL engine."""
    table_name = None
    pg_name = None
    pk_fields = None
    select_fields = None
    select_query = None

    table_existence_text = f"""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_schema = split_part(:pg_name, '.', 1)
            AND table_name = split_part(:pg_name, '.', 2)
        )

    """

    try:
        table_name, pg_name, pk_fields, select_fields = tm.table_meta_data(object_id, source_engine)

        # does the table exist in the PG target?
        with target_engine.connect() as conn:
            result = conn.execute(sa.text(table_existence_text), {"pg_name": pg_name})
            exists = result.scalar_one_or_none()

        if exists:
            # The table exists. Right now, we know what we'd like the target columns types
            # should be. Right here, we need to see what they actually are. We're going to
            # do our best to push what we've got into those holes. This doesn't always work

            target_columns = existing_target_columns(pg_name=pg_name, target_engine=target_engine)
            print (target_columns)

        else:
            if cfg.create_pg_target_when_not_exists:
                c_log(f"Table {pg_name} does not exist in PostgreSQL. Create it.")

                c_log(f"call tcs.get_create_table_script.")
                create_table_script = tcs.get_create_table_script(object_id, source_engine)

                c_log(f"CREATE TABLE script for {pg_name}:\n{create_table_script}")

                if not create_table_script:
                    raise ValueError(f"Could not generate CREATE TABLE script for object_id = {object_id}")

                # SqlAlchemy best practice:
                #           engine.connect() as conn: returns a Connection object that is a context manager.
                #           engine.begin() as conn: returns a Connection object that is a context manager and starts a transaction.
                # use .begin() for important operations that should be atomic, like creating a table. 
                # If the operation fails, the transaction will be rolled back.

                with target_engine.begin() as trgt_conn:
                    trgt_conn.execute(sa.text(create_table_script))

                # does it exist now?
                with target_engine.connect() as conn:
                    result = conn.execute(sa.text(table_existence_text), {"pg_name": pg_name})
                    exists = result.scalar_one_or_none()    

                if exists:
                    c_log(f"Successfully created table {pg_name} in PostgreSQL.")

                else:
                    c_log(f"Failed to create table {pg_name} in PostgreSQL.")
                    return table_name, False, msg

            else:
                msg = f"Skipped {table_name} -> {pg_name}: target does not exist and create_pg_target_when_not_exists is False."
                c_log(msg)
                return table_name, False, msg

        c_log(f"Processing table {table_name} (object_id = {object_id}) -> {pg_name}")

        # TRUNCATE the target table 
        with target_engine.begin() as trgt_conn:
            trgt_conn.execute(sa.text(f"TRUNCATE TABLE {pg_name}"))

        if select_fields is None:
            select_fields = select_cols(object_id, source_engine)

        if cfg.I_am_testing:
            page_row_count = 5

        else:
            page_row_count = cfg.chunk_size

        if pk_fields:
            page_no = 0 # page_no is zero-based.

            while True:
                select_query = f"""
                    SELECT {select_fields} 
                    FROM {table_name} 
                    ORDER BY {pk_fields}
                    OFFSET {page_no * cfg.chunk_size} ROWS
                    FETCH NEXT {page_row_count} ROWS ONLY;
                """

                if page_no == 0:
                    # print(f"select_query: {select_query} -- page_no={page_no}")
                    pass
                else:   
                    # print(f'-- page_no={page_no}')
                    pass
                    
                rows = pd.read_sql(select_query, source_engine)

                if not rows.empty:
                    rows.columns = [c.lower() for c in rows.columns]
                else:
                    break

                push_to_pg(rows, target_engine, pg_name)
                c_log(f"Fetched {len(rows)} rows from {table_name} -> {pg_name} (page {page_no})")

                page_no += 1

            return table_name, True, select_query

        select_query = f"""
            SELECT {select_fields} 
            FROM {table_name} 
        """
        rows = pd.read_sql(select_query, source_engine)
        return table_name, True, select_query

    except Exception as exc:
        c_log(
            f"ERROR: process_table: {table_name!r} pk_fields: {pk_fields!r} select_fields: {select_fields!r} "
        )
        c_log(f"Error processing table with {select_query!r}: {exc}")
        return f"object_id = {object_id}", False, str(exc)
