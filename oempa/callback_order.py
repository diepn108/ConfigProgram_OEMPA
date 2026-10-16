"""Pure decoding of bounded native order evidence; no acceptance decisions."""


KINDS = {1: "callback", 2: "on_requested", 3: "on_returned", 4: "first_callback", 5: "unique_required_ids_reached", 6: "first_duplicate", 7: "off_requested", 8: "off_call_entered", 9: "off_call_returned", 10: "final_callback_observed"}
FIELDS = ("event_index", "kind", "arrival_index", "cycle_id", "sample_count", "data_size", "signed", "bit_size", "status", "reserved")
SUMMARY = ("stored_events", "required_cycles", "total_callbacks", "dropped_callbacks", "dropped_markers", "unique_complete_event", "first_duplicate_event", "last_callback_event", "last_event")


def decode_callback_order(rows, summary, first):
    info = dict(zip(SUMMARY, summary))
    if len(summary) != 9 or not 0 <= info["stored_events"] <= 576 or not 1 <= info["required_cycles"] <= 2047:
        raise RuntimeError("Invalid callback order summary.")
    events = []
    for index in range(info["stored_events"]):
        event = dict(zip(FIELDS, rows[index * 10:(index + 1) * 10]))
        event["kind"] = KINDS[event["kind"]]
        if event["kind"] == "callback":
            event["signed"] = bool(event["signed"])
            event["malformed"] = bool(event["status"] & 1)
            event["unexpected"] = bool(event["status"] & 2)
            event["duplicate"] = bool(event["status"] & 4)
        events.append(event)
    callbacks_by_event = {event["event_index"]: event for event in events if event["kind"] == "callback"}
    first_events = list(first[:info["required_cycles"]])
    first_arrivals = [callbacks_by_event[index]["arrival_index"] if index in callbacks_by_event else None for index in first_events]
    return {
        **info, "schema_version": 1, "callback_capacity": 512, "marker_capacity": 64,
        "overflow": bool(info["dropped_callbacks"] or info["dropped_markers"]),
        "first_occurrence_events": first_events, "first_occurrence_arrivals": first_arrivals, "events": events,
        "ordering": "mutex-serialized native observations; 1-based indices, 0 means absent",
        "final_observation": "last callback observed at snapshot; not a callback-drain guarantee",
        "unique_boundary": "all required IDs observed, independent of record validity; not acceptance",
    }
