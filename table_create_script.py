import sqlalchemy
import cfg

c_log = cfg.log_to_the_log_file

script_maker = """
SET NOCOUNT ON;

DECLARE 
	  @object_id bigint = :oid -- the object_id of the table you want to create a script for

	-- Be careful below here. This is a script that, when executed against an actual @object_id, 
	-- will generate a corresponding postgres CREATE TABLE statement.
	-- Doug@HillsBrother.com

	, @cr CHAR(2) = CHAR(13) + CHAR(10) -- carriage return
	, @tab CHAR(1) = CHAR(9)
	, @name_column_width int = 40
	, @dt_column_width int = 15
	, @create_table_script varchar(max) 

SELECT @create_table_script = 'DO $$ ' + @cr + 'BEGIN' + @cr

-- for now, this is where the data type coercions are configured
-- It's possible to put values in here that don't make sence and,
-- therefore, won't give meaningful results.

DECLARE @dtc TABLE (
	  source_type varchar(32) PRIMARY KEY
	, pg_type varchar(32) NOT NULL
);

INSERT @dtc (source_type, pg_type)
VALUES 
	  ('bigint', 'bigint')
	, ('binary', 'binary')
	, ('bit', 'bit')
	, ('char', 'char')
	, ('date', 'date')
	, ('datetime', 'timestamp(3)')
	, ('datetime2', 'timestamp(3)')
	, ('datetimeoffset', 'datetimeoffset')
	, ('decimal', 'decimal')
	, ('float', 'float')
	, ('geography', 'geography')
	, ('geometry', 'geometry')
	, ('hierarchyid', 'hierarchyid')
	, ('image', 'image')
	, ('int', 'bigint')
	, ('json', 'json')
	, ('money', 'money')
	, ('nchar', 'text')
	, ('ntext', 'text')
	, ('numeric', 'numeric')
	, ('nvarchar', 'text')
	, ('real', 'real')
	, ('smalldatetime', 'timestamp(3)')
	, ('smallint', 'smallint')
	, ('smallmoney', 'smallmoney')
	, ('sysname', 'text')
	, ('text', 'text')
	, ('time', 'timestamp(3)')
	, ('timestamp', 'bigserial') -- ?
	, ('tinyint', 'bigint')
	, ('uniqueidentifier', 'uuid')
	, ('varbinary', 'bytea')
	, ('varchar', 'text')
	, ('vector', 'vector')
	, ('xml', 'xml')	 

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
	+ dtc.[pg_type]
	+ CASE 
		WHEN @dt_column_width <= LEN(dtc.[pg_type])
		THEN ' ' 
		ELSE REPLICATE(' ', @dt_column_width - LEN(dtc.[pg_type]))
	  END
	+ CASE c.is_nullable
		WHEN 1 THEN '    NULL'
		ELSE 'NOT NULL'
	  END
	+ @cr
FROM sys.tables as t
INNER JOIN sys.columns as c
	ON t.object_id = c.object_id
INNER JOIN sys.types as st
	ON c.system_type_id = st.system_type_id
LEFT OUTER JOIN @dtc as dtc
	ON st.[name] = dtc.source_type
WHERE t.object_id = @object_id
AND dtc.source_type NOT IN ('sysname')
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

/*
	this PRINT command gets the script to appear in the messages tab of
	SSMS. Un-comment this if you need to test this in SSMS. Un-commenting
	it here (in the python script) would likely break the execution.

	PRINT @create_table_script;
*/

SELECT @create_table_script as create_table_script;
"""

def get_create_table_script(object_id: int, source_engine: sqlalchemy.engine.base.Engine) -> str:
    """Return a CREATE TABLE script for the given SQL Server table object_id."""
    script = script_maker.replace(':oid', str(object_id))
    c_log(f"Generating CREATE TABLE script for object_id = {object_id}", script)

    try:
        with source_engine.connect() as conn:
            # Execute the script and fetch the single result
            result = conn.execute(sqlalchemy.text(script))
            
            # Fetch the single row
            row = result.fetchone()
            
            # The script returns one column named 'create_table_script'
            create_table_script = row[0] if row else None
            
            # Close the result
            result.close()
        
    except Exception as e:
        c_log(f"Error executing CREATE TABLE script for object_id = {object_id}", e)
        raise

    #c_log(f"CREATE TABLE script for object_id = {object_id}", f"{create_table_script}")
    return create_table_script or ""
