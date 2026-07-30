import cfg
import sqlalchemy as sa

c_log = cfg.log_to_the_log_file

def existing_target_columns(
    pg_name: str, 
    target_engine: sa.engine.base.Engine
) -> dict[str, str]:
    c_log(f"existing_target_columns {pg_name}")        
    schema, table = pg_name.split('.')

    column_enumeration_text = """
        SELECT c.column_name, c.data_type 
        FROM information_schema.columns as c
        WHERE c.table_schema = :schema
        AND c.table_name = :table;
    """

    #c_log(f'existing target column data types {pg_name}', column_enumeration_text)
    
    try:
        with target_engine.connect() as conn:
            c_log(f'about to execute {pg_name}')
            result = conn.execute(
                sa.text(column_enumeration_text), 
                {"schema": schema, "table": table}
            )

            # Log what type of result we have
            #c_log('Result type:', str(type(result)))
            #c_log('Result attributes:', str(dir(result)))
        

            rows = result.fetchall()
            #c_log('fetchall() returned:', str(rows))
            #c_log('fetchall() length:', str(len(rows)))
            #c_log(f'column count ', str(rows.count()))

            column_dict = {row[0]: row[1] for row in rows}
            #c_log(f'Column dictionary:  {pg_name}', str(column_dict))
            return column_dict

    except Exception as e:
        c_log(f"Failed executing column enumeration {pg_name}", {e})        
        raise RuntimeError(f"Failed executing column enumeration {pg_name}: {e}")   

    finally:
        conn.close()     

