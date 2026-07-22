# SS_2_PG

```text
This little script is for migrating data from a SQL Server database to 
a PG one. 

There is a setting in cfg.py (create_pg_target_when_not_exists)
When this is false and there is no target on PG, the table will
simply be skipped.

The target table in the PG database will be truncated prior to data transfer.
It would be best to not point this at an important target. This is only
to facilitate populating a PG database for development purposes.

Tables with PKs are paged. Heaps are brought over in a single dataframe
The important knobs/settings are in cfg.py

IMPORTANT: 
    The user defined in the cfg for the sql server connection must have the
    ability to VIEW DATABASE STATE

    Check: GRANT VIEW DATABASE STATE TO [YourUser]

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
```

2. Install the project:

```bash
pip install -e .
```

3. Run the application:

```bash
python ss_2_pg.py 
```
