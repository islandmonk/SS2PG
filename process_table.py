import pandas as pd
import sqlalchemy as sa
import cfg
import table_create_script as tcs
import table_metadata as tm

def push_to_pg(df, target_engine: sa.engine.base.Engine, two_part_table_name: str):
    table = two_part_table_name.split('.')[-1]  
    schema = two_part_table_name.split('.')[0]  
    columns = ", ".join(df.columns)

    coercion = {
        "bigint": "bigint",
        "int": "bigint",
        "int16": "bigint",
        "int32": "bigint",
        "int64": "bigint",
        "smallint": "bigint",
        "tinyint": "bigint",
        "bit": "boolean",
        "bool": "boolean",
        "decimal": "numeric",
        "numeric": "numeric",
        "money": "numeric",
        "smallmoney": "numeric",
        "float": "double precision",
        "float64": "double precision",
        "float32": "double precision",
        "real": "double precision",
        "date": "date",
        "datetime64[us]":"timestamp",
        "datetime": "timestamp",
        "datetime2": "timestamp",
        "smalldatetime": "timestamp",
        "str": "text",
        "time": "time",
        "char": "text",
        "nchar": "text",
        "varchar": "text",
        "nvarchar": "text",
        "text": "text",
        "object": "text",
        "ntext": "text",
        "binary": "bytea",
        "varbinary": "bytea",
        "image": "bytea",
        "uniqueidentifier": "uuid",
    }

    rows = []
    for row in df.itertuples(index=False, name=None):
        values = []
        for val, col in zip(row, df.columns):
            dtype = str(df[col].dtype)
            pg_type = coercion.get(dtype, "")

            if not pg_type:
                print(f"What should I do with this dtype? {dtype} -> {pg_type}")

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
        
    print(f"Pushing {len(df)} rows to {schema}.{table}")
    cfg.log_to_the_log_file(the_big_insert_command)
    #print(the_big_insert_command)
    #print("------------------------------------")

    with target_engine.begin() as conn:
        result = conn.execute(sa.text(the_big_insert_command))
        print(f"result: {result.rowcount}")

    #raise RuntimeError("stop here")

    # df.to_sql(table, con=target_engine, schema=schema, if_exists='append', index=False, method=insert_method)

def process_table(
    object_id: int, 
    source_engine: sa.engine.base.Engine, 
    target_engine: sa.engine.base.Engine
) -> tuple[str, bool, str]:
    #print(f"process_table object_id = {object_id}")

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

            # print(f"Table {pg_name} exists in PostgreSQL: {exists}")

        if not exists:
            print(f"Table {pg_name} does not exist in PostgreSQL. Creating it.")
            if cfg.create_pg_target_when_not_exists:
                create_table_script = tcs.get_create_table_script(object_id, source_engine)

                print(f"CREATE TABLE script for {pg_name}:\n{create_table_script}")

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
                    print(f"Successfully created table {pg_name} in PostgreSQL.")
                else:
                    msg = f"Failed to create table {pg_name} in PostgreSQL."
                    print(msg)
                    return table_name, False, msg

            else:
                msg = f"Skipped {table_name} -> {pg_name}: target does not exist and create_pg_target_when_not_exists is False."
                print(msg)
                return table_name, False, msg

        print(f"Processing table {table_name} (object_id={object_id}) -> {pg_name}")

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
            page_no = 0

            while True:
                select_query = f"""
                    SELECT {select_fields} 
                    FROM {table_name} 
                    ORDER BY {pk_fields}
                    OFFSET {page_no * cfg.chunk_size} ROWS -- page_no is zero-based.
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
                print(f"Fetched {len(rows)} rows from {table_name} -> {pg_name} (page {page_no})")

                page_no += 1

            return table_name, True, select_query

        select_query = f"""
            SELECT {select_fields} 
            FROM {table_name} 
        """
        rows = pd.read_sql(select_query, source_engine)
        return table_name, True, select_query

    except Exception as exc:
        print(
            f"table_name: {table_name!r} pk_fields: {pk_fields!r} select_fields: {select_fields!r} "
        )
        print(f"Error processing table with {select_query!r}: {exc}")
        return f"object_id = {object_id}", False, str(exc)
