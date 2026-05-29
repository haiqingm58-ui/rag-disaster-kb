"""Re-export from disaster submodule for backward compatibility."""
from .disaster.writer import (
    init_schema,
    merge_event,
    merge_attribute,
    merge_attribute_dedup,
    merge_location,
    merge_source_document,
    link_has_attribute,
    link_occurred_at,
    link_reported_by,
    link_evidenced_by,
    write_extraction_result,
    get_event_context,
    query_recent_events,
    check_connection,
    close_driver,
)
