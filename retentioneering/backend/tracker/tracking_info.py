from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import datetime
from typing import Generator


def get_index() -> Generator:
    idx = 1
    while True:
        yield idx
        idx += 1


index = get_index()


@dataclass
class TrackingInfo:
    client_session_id: str
    event_custom_name: str
    event_name: str
    event_value: str
    params: dict[str, str] | list[str]
    scope: str
    event_time: datetime
    # marketing_session_type_3_id: str # @FIXME: what is this? Vladimir Makhanov.

    event_date_local: str = ""
    # event_date_moscow: str    # @TODO: implement. Vladimir Makhanov
    user_id: str = ""
    event_day_week: int = 0
    event_timestamp: int = 0
    event_timestamp_ms: int = 0
    source: str = "rete_transition_graph"
    version: str = "3.0.0b3"
    os: str = platform.system()
    index: int = 0

    def __post_init__(self) -> None:
        current_time = datetime.now()
        event_timestamp = current_time.timestamp()
        tz_string = current_time.astimezone().tzname()
        local_printable_date = current_time.strftime("%m/%d/%Y %H:%M:%S")
        self.event_date_local = f"{local_printable_date} GMT{tz_string}"
        self.event_day_week = current_time.weekday()
        self.event_timestamp = int(event_timestamp)
        self.event_timestamp_ms = int(event_timestamp * 1000)
        self.user_id = f"{self.client_session_id}|none|none|none"
        self.index = next(index)
