# SS_2_PG

# This little script is for migrating data from a SQL Server database to 
# a PG one. It is expected that for every table migrated, there is already
# a Postgres table with a schema that can handle the dataframes coming from
# SQL Server.
# the target table in the PG database will be truncated prior to data motion.
# Tables with PKs are paged. Heaps are brought over in a single dataframe
# The important knobs/settings are in cfg.py

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
# or
ss2pg 
```
