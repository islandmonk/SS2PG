import pandas as pd
import sqlalchemy as sa
import cfg
import table_create_script as tcs
import table_metadata as tm


def push_to_pg(df, target_engine: sa.engine.base.Engine, table_name: str):
    # This gives us a single place to add logging, retries, or batching later.
    df.to_sql(table_name, con=target_engine, if_exists='append', index=False)

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

    try:
        table_name, pg_name, pk_fields, select_fields = tm.table_meta_data(object_id, source_engine)

        # does the table exist in the PG target?
        with target_engine.connect() as conn:
            result = conn.execute(sa.text("""
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
                create_table_script = tcs.get_create_table_script(object_id, source_engine)

                if not create_table_script:
                    raise ValueError(f"Could not generate CREATE TABLE script for object_id={object_id}")

                with target_engine.connect() as conn:
                    conn.execute(sa.text(create_table_script))
                print(f"Created table {pg_name} in PostgreSQL.")
            else:
                msg = f"Skipped {table_name} -> {pg_name}: target does not exist and create_pg_tables is False."
                print(msg)
                return table_name, False, msg

        print(f"Processing table {table_name} (object_id={object_id}) -> {pg_name}")

        if select_fields is None:
            select_fields = select_cols(object_id, source_engine)

        if pk_fields:
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
        return f"object_id={object_id}", False, str(exc)
