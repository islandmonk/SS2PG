import cfg
import sqlalchemy as sa

c_log = cfg.log_to_the_log_file

def pg_table_exists (pg_name: str, target_engine:sa.engine.base.Engine) -> bool:
    c_log(f"pg_table_exists {pg_name}")        
    schema, table = pg_name.split('.')

    table_existence_text = f"""
        SELECT EXISTS (
            SELECT 1::int 
            FROM information_schema.tables 
            WHERE table_schema = '{schema}'
            AND table_name = '{table}'
        );

    """
    # c_log(f"table existence script {pg_name}", table_existence_text)        

    try:
        with target_engine.connect() as conn:
            result = conn.execute(sa.text(table_existence_text))
            exists = result.scalar_one_or_none()   
            c_log(f"the answer to the question, does {pg_name} exist? is [{exists}]")        

        return exists

    except Exception as e: 
        c_log(f"Failed checking table's existence {pg_name}", e)        
        raise RuntimeError(f"Failed checking table's existence  {pg_name}: {e}")        
