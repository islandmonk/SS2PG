from dataclasses import dataclass

@dataclass
class TableMetadata:
    """Metadata for a database table."""
    sql_server_name: str
    object_id: int
    pg_name: str
    pk_fields: str
    select_fields: str
    expected_row_count: int