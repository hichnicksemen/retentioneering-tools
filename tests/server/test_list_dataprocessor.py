import json

from src.backend.callback import list_dataprocessor


class TestListDataprocessors:
    def test_list_dataprocessors(self) -> None:
        correct_data = [
            {
                "name": "StubProcessor",
                "params": {"a": {"default": None, "name": "A", "optional": False, "widget": "array"}},
            },
            {
                "name": "CollapseLoops",
                "params": {
                    "full_collapse": {"name": "full_collapse", "optional": True, "widget": "boolean"},
                    "timestamp_aggregation_type": {
                        "name": "timestamp_aggregation_type",
                        "optional": True,
                        "widget": "string",
                    },
                },
            },
            {
                "name": "DeleteUsersByPathLength",
                "params": {
                    "cutoff": {
                        "name": "cutoff",
                        "optional": True,
                        "params": [
                            {"widget": "float"},
                            {
                                "params": [
                                    "Y",
                                    "M",
                                    "W",
                                    "D",
                                    "h",
                                    "m",
                                    "s",
                                    "ms",
                                    "us",
                                    "\u03bcs",
                                    "ns",
                                    "ps",
                                    "fs",
                                    "as",
                                ],
                                "widget": "enum",
                            },
                        ],
                        "widget": "time_widget",
                    },
                    "events_num": {"name": "events_num", "optional": True, "widget": "integer"},
                },
            },
            {
                "name": "LostUsersEvents",
                "params": {
                    "lost_cutoff": {
                        "name": "lost_cutoff",
                        "optional": True,
                        "params": [
                            {"widget": "float"},
                            {
                                "params": [
                                    "Y",
                                    "M",
                                    "W",
                                    "D",
                                    "h",
                                    "m",
                                    "s",
                                    "ms",
                                    "us",
                                    "\u03bcs",
                                    "ns",
                                    "ps",
                                    "fs",
                                    "as",
                                ],
                                "widget": "enum",
                            },
                        ],
                        "widget": "time_widget",
                    },
                    "lost_users_list": {
                        "name": "lost_users_list",
                        "optional": True,
                        "widget": "list_of_int",
                    },
                },
            },
            {
                "name": "NegativeTarget",
                "params": {
                    "negative_function": {
                        "_source_code": "",
                        "name": "negative_function",
                        "optional": True,
                        "widget": "function",
                    },
                    "negative_target_events": {
                        "name": "negative_target_events",
                        "optional": False,
                        "widget": "list_of_string",
                    },
                },
            },
            {
                "name": "NewUsersEvents",
                "params": {
                    "new_users_list": {
                        "name": "new_users_list",
                        "disable_value": "all",
                        "optional": False,
                        "widget": "list_of_int",
                    }
                },
            },
            {
                "name": "PositiveTarget",
                "params": {
                    "positive_function": {
                        "_source_code": "",
                        "name": "positive_function",
                        "optional": True,
                        "widget": "function",
                    },
                    "positive_target_events": {
                        "name": "positive_target_events",
                        "optional": False,
                        "widget": "list_of_string",
                    },
                },
            },
            {
                "name": "SplitSessions",
                "params": {
                    "mark_truncated": {"name": "mark_truncated", "optional": True, "widget": "boolean"},
                    "session_col": {"name": "session_col", "optional": False, "widget": "string"},
                    "session_cutoff": {
                        "name": "session_cutoff",
                        "optional": False,
                        "params": [
                            {"widget": "float"},
                            {
                                "params": [
                                    "Y",
                                    "M",
                                    "W",
                                    "D",
                                    "h",
                                    "m",
                                    "s",
                                    "ms",
                                    "us",
                                    "\u03bcs",
                                    "ns",
                                    "ps",
                                    "fs",
                                    "as",
                                ],
                                "widget": "enum",
                            },
                        ],
                        "widget": "time_widget",
                    },
                },
            },
            {"name": "StartEndEvents", "params": {}},
            {
                "name": "TruncatePath",
                "params": {
                    "drop_after": {"name": "drop_after", "optional": True, "widget": "string"},
                    "drop_before": {"name": "drop_before", "optional": True, "widget": "string"},
                    "occurrence_after": {"name": "occurrence_after", "optional": True, "widget": "string"},
                    "occurrence_before": {"name": "occurrence_before", "optional": True, "widget": "string"},
                    "shift_after": {"name": "shift_after", "optional": True, "widget": "integer"},
                    "shift_before": {"name": "shift_before", "optional": True, "widget": "integer"},
                },
            },
            {
                "name": "TruncatedEvents",
                "params": {
                    "left_truncated_cutoff": {
                        "name": "left_truncated_cutoff",
                        "optional": True,
                        "params": [
                            {"widget": "float"},
                            {
                                "params": [
                                    "Y",
                                    "M",
                                    "W",
                                    "D",
                                    "h",
                                    "m",
                                    "s",
                                    "ms",
                                    "us",
                                    "\u03bcs",
                                    "ns",
                                    "ps",
                                    "fs",
                                    "as",
                                ],
                                "widget": "enum",
                            },
                        ],
                        "widget": "time_widget",
                    },
                    "right_truncated_cutoff": {
                        "name": "right_truncated_cutoff",
                        "optional": True,
                        "params": [
                            {"widget": "float"},
                            {
                                "params": [
                                    "Y",
                                    "M",
                                    "W",
                                    "D",
                                    "h",
                                    "m",
                                    "s",
                                    "ms",
                                    "us",
                                    "\u03bcs",
                                    "ns",
                                    "ps",
                                    "fs",
                                    "as",
                                ],
                                "widget": "enum",
                            },
                        ],
                        "widget": "time_widget",
                    },
                },
            },
            {
                "name": "HelperAddColProcessor",
                "params": {
                    "column_name": {"name": "column_name", "optional": False, "widget": "string"},
                    "event_name": {"name": "event_name", "optional": False, "widget": "string"},
                },
            },
            {
                "name": "NoHelperAddColProcessor",
                "params": {
                    "column_name": {"name": "column_name", "optional": False, "widget": "string"},
                    "event_name": {"name": "event_name", "optional": False, "widget": "string"},
                },
            },
            {
                "name": "DeleteProcessor",
                "params": {"name": {"name": "name", "optional": False, "widget": "string"}},
            },
            {"name": "FilterEvents", "params": {}},
            {
                "name": "GroupEvents",
                "params": {
                    "event_name": {"name": "event_name", "optional": False, "widget": "string"},
                    "event_type": {"name": "event_type", "optional": True, "widget": "string"},
                },
            },
            {
                "name": "StubProcessorPGraph",
                "params": {"a": {"default": None, "name": "A", "optional": False, "widget": "array"}},
            },
        ]

        assert json.dumps(correct_data, sort_keys=True, indent=4, separators=(",", ": ")) == json.dumps(
            list_dataprocessor(payload={}), sort_keys=True, indent=4, separators=(",", ": ")
        )
