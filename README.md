# SS_2_PG

```text
This little script is for migrating data from a SQL Server database to 
a PG one. 

There is a setting in cfg.py (create_pg_target_when_not_exists)
When this is false and there is no target on PG, the table is
simply skipped.

The target table in the PG database will be truncated prior to data transfer.
It would be best to not point this at an important target. This is only
to facilitate populating a PG database for development purposes.

I don't see any reason against this eventually hardening to the point that 
it could be used to orchestrate ETL processes or other sorts of jobs where,
for whatever reason, the available tools didn't get you all the way there.

Tables with PKs are paged. Heaps are brought over in a single dataframe
The important knobs/settings are in cfg.py

The SQL commands executed agains both engines are crafted in this script.
These scripts are exposed in the logging file. Some of the commands get huge.
You can tell it how much of the command you want to see in the log.

see: cfg.truncated_command_length

Data type coercion is configurable. I'll have a page dedicated to just 
that so it is more straight forward to maintain.
Right now, the only way to mess with the coercion configuration is through
text manipulation in the TSQL variable @dtc's definition (table_create_script.py). 
You can definitely experiment with that. 

IMPORTANT: 
    The user defined in the cfg for the sql server connection must have the
    ability to VIEW DATABASE STATE

    Check: GRANT VIEW DATABASE STATE TO [YourUser]

Progress bars are added for your viewing enjoyment. They seem to work clumbsily when 
multi-threading but they 'work.' 

requires-python >= 3.10
On different platforms
Linux: need unixodbc (or equivalent) plus the SQL Server ODBC driver
Windows: the driver manager is usually present, but users still need the SQL Server ODBC driver
Doug@HillsBrother.com
```

## Run locally

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
# for fish: source .venv/bin/activate.fish
```

2. Install the project:

```bash
pip install -e .
```

3. Run the application:

```bash
python ss_2_pg.py 
```
