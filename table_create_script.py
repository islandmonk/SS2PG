import sqlalchemy

script_maker = """
DECLARE 
	  @object_id bigint = :oid -- the object_id of the table you want to create a script for

      -- Don't touch anything below here unless you know what you're doing. This is a script 
      -- that will generate a (postgresql) CREATE TABLE statement for the given object_id.
      -- Doug@HillsBrother.com

	, @cr CHAR(2) = CHAR(13) + CHAR(10) -- carriage return
	, @tab CHAR(1) = CHAR(9)
	, @name_column_width int = 40
	, @dt_column_width int = 10
	, @create_table_script varchar(max) 

SELECT @create_table_script = 'DO $$ ' + @cr + 'BEGIN' + @cr

;WITH x as (
	SELECT 
		  t.name as [table_name]
		, CASE s.[name]
			WHEN 'dbo' THEN 'public'
			ELSE s.[name]
		  END as [schema_name]
	FROM sys.tables as t
	INNER JOIN sys.schemas as s
		ON t.schema_id = s.schema_id
	WHERE t.object_id = @object_id
)
SELECT @create_table_script += 'CREATE SCHEMA IF NOT EXISTS '
	+ x.[schema_name] + ';' + @cr + @cr
	+ 'CREATE TABLE IF NOT EXISTS '
	+ x.[schema_name]
	+ '.'
	+ x.[table_name]
	+ ' ( ' + @cr
FROM x;

SELECT TOP (1) @name_column_width = LEN(c.name) + 4
FROM sys.columns as c
WHERE c.object_id = @object_id
ORDER BY LEN(c.name) DESC;

SELECT @create_table_script +=
	  @tab
	+ CASE c.column_id
		WHEN 1 THEN '  '
		ELSE ', '
	  END
	+ LOWER(c.name) 
	-- make it pretty
	+ REPLICATE(' ', @name_column_width - LEN(c.name))
	+ ty.[target_type]
	+ REPLICATE(' ', @dt_column_width - LEN(ty.[target_type]))
	+ CASE c.is_nullable
		WHEN 1 THEN '    NULL'
		ELSE 'NOT NULL'
	  END
	+ @cr
FROM sys.tables as t
INNER JOIN sys.columns as c
	ON t.object_id = c.object_id
INNER JOIN (
	SELECT 
		  x.system_type_id
		, x.name as source_type
		, CASE
			WHEN x.[name] LIKE '%int' THEN 'bigint' 
			WHEN x.[name] LIKE '%varchar%' THEN 'text'
			WHEN x.[name] LIKE '%datetime%' THEN 'timestamp'
			ELSE x.[name]
		  END as target_type 
	FROM sys.types as x
) as ty
	ON c.system_type_id = ty.system_type_id
WHERE t.object_id = @object_id
AND ty.source_type NOT IN ('sysname')
ORDER BY c.column_id;

-- do we have a primary key?
IF EXISTS (
	SELECT * 
	FROM sys.indexes as i
	WHERE i.is_primary_key = 1
	AND i.object_id = @object_id
)
BEGIN
	SELECT @create_table_script += @tab + ', PRIMARY KEY (' ;

	SELECT @create_table_script += 
		  CASE ic.index_column_id
			WHEN 1 THEN ''
			ELSE ', '
		  END
		+ c.name
		+ CASE ic.is_descending_key
			WHEN 1 THEN ' DESC' 
			ELSE ''
		  END
	FROM sys.indexes as i
	INNER JOIN sys.index_columns as ic
		ON i.object_id = ic.object_id
		AND i.index_id = ic.index_id
	INNER JOIN sys.columns as c
		ON i.object_id = c.object_id
		AND ic.column_id = c.column_id
	WHERE i.is_primary_key = 1
	AND i.object_id = @object_id
	ORDER BY i.object_id, ic.index_column_id;

	SELECT @create_table_script += ') ' + @cr;
END

SELECT @create_table_script += ');
END
$$ LANGUAGE plpgsql;'

-- this will get the script to appear in the messages tab of SSMS.
-- un-comment this out if you need to test this in ssms.
-- Print @create_table_script;

SELECT @create_table_script as create_table_script;
"""

def get_create_table_script(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> str:
    """Return a CREATE TABLE script for the given SQL Server table object_id."""
    # print(f"Generating CREATE TABLE script for object_id = {object_id}")
    with source_engine.connect() as conn:
        # print(f"CREATE TABLE script for object_id = {object_id}:\n{script_maker}") 
        result = conn.execute(sqlalchemy.text(script_maker), {"oid": object_id})
        # print(f"result: {result}")
        create_table_script = result.scalar_one_or_none()
        # print(f"CREATE TABLE script for object_id = {object_id}:\n{create_table_script}")

    return create_table_script or ""    
