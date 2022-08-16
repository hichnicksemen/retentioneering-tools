from __future__ import annotations

import unittest

import pandas as pd

from src.eventstream.eventstream import Eventstream
from src.eventstream.schema import EventstreamSchema, RawDataSchema

from .simple_processors import DeleteEvents, SimpleGroup


class SimpleProcessorsTest(unittest.TestCase):
    def test_simple_group(self):
        source_df = pd.DataFrame(
            [
                {
                    "event_name": "pageview",
                    "event_timestamp": "2021-10-26 12:00",
                    "user_id": "1",
                },
                {
                    "event_name": "cart_btn_click",
                    "event_timestamp": "2021-10-26 12:02",
                    "user_id": "1",
                },
                {
                    "event_name": "pageview",
                    "event_timestamp": "2021-10-26 12:03",
                    "user_id": "1",
                },
                {
                    "event_name": "plus_icon_click",
                    "event_timestamp": "2021-10-26 12:04",
                    "user_id": "1",
                },
            ]
        )

        source = Eventstream(
            raw_data=source_df,
            schema=EventstreamSchema(),
            raw_data_schema=RawDataSchema(
                event_name="event_name",
                event_timestamp="event_timestamp",
                user_id="user_id",
            ),
        )

        source_df = source.to_dataframe()

        group = SimpleGroup(
            params={
                "event_name": "add_to_cart",
                "event_type": "group_alias",
                "filter": lambda df, schema: df[schema.event_name].isin(  # type: ignore
                    ["cart_btn_click", "plus_icon_click"]
                ),
            }
        )

        result = group.apply(source)
        result_df: pd.DataFrame = result.to_dataframe()

        events_names: list[str] = result_df[result.schema.event_name].to_list()
        events_type: list[str] = result_df[result.schema.event_type].to_list()
        refs: list[str] = result_df["ref_0"].to_list()

        self.assertEqual(events_names, ["add_to_cart", "add_to_cart"])
        self.assertEqual(events_type, ["group_alias", "group_alias"])
        self.assertEqual(
            refs,
            [
                source_df.iloc[1][source.schema.event_id],
                source_df.iloc[3][source.schema.event_id],
            ],
        )

    def test_delete_factory(self):
        source_df = pd.DataFrame(
            [
                {
                    "event_name": "pageview",
                    "event_timestamp": "2021-10-26 12:00",
                    "user_id": "1",
                },
                {
                    "event_name": "cart_btn_click",
                    "event_timestamp": "2021-10-26 12:02",
                    "user_id": "1",
                },
                {
                    "event_name": "pageview",
                    "event_timestamp": "2021-10-26 12:03",
                    "user_id": "1",
                },
                {
                    "event_name": "plus_icon_click",
                    "event_timestamp": "2021-10-26 12:04",
                    "user_id": "1",
                },
            ]
        )

        source = Eventstream(
            raw_data=source_df,
            schema=EventstreamSchema(),
            raw_data_schema=RawDataSchema(
                event_name="event_name",
                event_timestamp="event_timestamp",
                user_id="user_id",
            ),
        )

        delete_factory = DeleteEvents(
            {
                "filter": lambda df, schema: df[schema.event_name].isin(  # type: ignore
                    ["cart_btn_click", "plus_icon_click"]
                )
            }
        )

        result = delete_factory.apply(source)
        result_df = result.to_dataframe(show_deleted=True)
        events_names: list[str] = result_df[result.schema.event_name].to_list()

        self.assertEqual(events_names, ["cart_btn_click", "plus_icon_click"])
