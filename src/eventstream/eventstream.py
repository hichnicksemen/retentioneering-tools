# flake8: noqa
from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from typing import Any, Callable, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
from matplotlib.axes import SubplotBase

from src.constants import DATETIME_UNITS
from src.eventstream.schema import EventstreamSchema, RawDataSchema
from src.eventstream.types import EventstreamType, RawDataSchemaType, Relation
from src.tooling.clusters import Clusters
from src.tooling.cohorts import Cohorts
from src.tooling.funnel import Funnel
from src.tooling.stattests import TEST_NAMES, StatTests
from src.tooling.step_matrix import StepMatrix
from src.tooling.step_sankey import StepSankey
from src.tooling.timedelta_hist import AGGREGATION_NAMES, TimedeltaHist
from src.tooling.user_lifetime_hist import UserLifetimeHist
from src.utils import get_merged_col
from src.utils.list import find_index

from .helpers import (
    CollapseLoopsHelperMixin,
    DeleteUsersByPathLengthHelperMixin,
    FilterHelperMixin,
    GroupHelperMixin,
    LostUsersHelperMixin,
    NegativeTargetHelperMixin,
    NewUsersHelperMixin,
    PositiveTargetHelperMixin,
    RenameHelperMixin,
    SplitSessionsHelperMixin,
    StartEndHelperMixin,
    TruncatedEventsHelperMixin,
    TruncatePathHelperMixin,
)

IndexOrder = List[Optional[str]]
FeatureType = Literal["tfidf", "count", "frequency", "binary", "time", "time_fraction", "external"]
NgramRange = Tuple[int, int]
Method = Literal["kmeans", "gmm"]


DEFAULT_INDEX_ORDER: IndexOrder = [
    "profile",
    "path_start",
    "new_user",
    "existing_user",
    "truncated_left",
    "session_start",
    "session_start_truncated",
    "group_alias",
    "raw",
    "raw_sleep",
    None,
    "synthetic",
    "synthetic_sleep",
    "positive_target",
    "negative_target",
    "session_end_truncated",
    "session_end",
    "session_sleep",
    "truncated_right",
    "absent_user",
    "lost_user",
    "path_end",
]

RAW_COL_PREFIX = "raw_"
DELETE_COL_NAME = "_deleted"


# TODO проработать резервирование колонок


class Eventstream(
    CollapseLoopsHelperMixin,
    DeleteUsersByPathLengthHelperMixin,
    FilterHelperMixin,
    GroupHelperMixin,
    LostUsersHelperMixin,
    NegativeTargetHelperMixin,
    NewUsersHelperMixin,
    PositiveTargetHelperMixin,
    SplitSessionsHelperMixin,
    StartEndHelperMixin,
    TruncatedEventsHelperMixin,
    TruncatePathHelperMixin,
    RenameHelperMixin,
    EventstreamType,
):
    schema: EventstreamSchema
    index_order: IndexOrder
    relations: List[Relation]
    __raw_data_schema: RawDataSchemaType
    __events: pd.DataFrame | pd.Series[Any]
    __clusters: Clusters | None = None
    __funnel: Funnel | None = None
    __cohorts: Cohorts | None = None
    __step_matrix: StepMatrix | None = None
    __sankey: StepSankey | None = None
    __stattests: StatTests | None = None
    __timedelta_hist: TimedeltaHist | None = None
    __user_lifetime_hist: UserLifetimeHist | None = None

    def __init__(
        self,
        raw_data: pd.DataFrame | pd.Series[Any],
        raw_data_schema: RawDataSchemaType | None = None,
        schema: EventstreamSchema | None = None,
        prepare: bool = True,
        index_order: Optional[IndexOrder] = None,
        relations: Optional[List[Relation]] = None,
        user_sample_size: Optional[int | float] = None,
        user_sample_seed: Optional[int] = None,
    ) -> None:
        self.__clusters = None
        self.__funnel = None
        self.schema = schema if schema else EventstreamSchema()

        if not raw_data_schema:
            raw_data_schema = RawDataSchema()
            if "event_type" in raw_data.columns:
                raw_data_schema.event_type = "event_type"
        self.__raw_data_schema = raw_data_schema

        if user_sample_size is not None:
            raw_data = self.__sample_user_paths(raw_data, raw_data_schema, user_sample_size, user_sample_seed)
        if not index_order:
            self.index_order = DEFAULT_INDEX_ORDER
        else:
            self.index_order = index_order
        if not relations:
            self.relations = []
        else:
            self.relations = relations
        self.__events = self.__prepare_events(raw_data) if prepare else raw_data
        self.index_events()

    def copy(self) -> Eventstream:
        return Eventstream(
            raw_data_schema=self.__raw_data_schema.copy(),
            raw_data=self.__events.copy(),
            schema=self.schema.copy(),
            prepare=False,
            index_order=self.index_order.copy(),
            relations=self.relations.copy(),
        )

    def append_eventstream(self, eventstream: Eventstream) -> None:  # type: ignore
        if not self.schema.is_equal(eventstream.schema):
            raise ValueError("invalid schema: joined eventstream")

        curr_events = self.to_dataframe(raw_cols=True, show_deleted=True)
        new_events = eventstream.to_dataframe(raw_cols=True, show_deleted=True)

        curr_deleted_events = curr_events[curr_events[DELETE_COL_NAME] == True]
        new_deleted_events = new_events[new_events[DELETE_COL_NAME] == True]
        deleted_events = pd.concat([curr_deleted_events, new_deleted_events])
        deleted_events = deleted_events.drop_duplicates(subset=[self.schema.event_id])

        merged_events = pd.merge(
            curr_events,
            new_events,
            left_on=self.schema.event_id,
            right_on=self.schema.event_id,
            how="outer",
            indicator=True,
        )

        left_events = merged_events[(merged_events["_merge"] == "left_only") | (merged_events["_merge"] == "both")]
        right_events = merged_events[(merged_events["_merge"] == "right_only")]

        left_raw_cols = self.get_raw_cols()
        right_raw_cols = eventstream.get_raw_cols()
        cols = self.schema.get_cols()

        result_left_part = pd.DataFrame()
        result_right_part = pd.DataFrame()

        for col in cols:
            result_left_part[col] = get_merged_col(df=left_events, colname=col, suffix="_x")
            result_right_part[col] = get_merged_col(df=right_events, colname=col, suffix="_y")

        for col in left_raw_cols:
            result_left_part[col] = get_merged_col(df=left_events, colname=col, suffix="_x")

        for col in right_raw_cols:
            result_right_part[col] = get_merged_col(df=right_events, colname=col, suffix="_y")

        result_left_part[DELETE_COL_NAME] = get_merged_col(df=left_events, colname=DELETE_COL_NAME, suffix="_x")
        result_right_part[DELETE_COL_NAME] = get_merged_col(df=right_events, colname=DELETE_COL_NAME, suffix="_y")

        self.__events = pd.concat([result_left_part, result_right_part])
        self.soft_delete(deleted_events)
        self.index_events()

    def join_eventstream(self, eventstream: Eventstream) -> None:  # type: ignore
        if not self.schema.is_equal(eventstream.schema):
            raise ValueError("invalid schema: joined eventstream")

        relation_i = find_index(
            input_list=eventstream.relations,
            cond=lambda rel: rel["eventstream"] == self,
        )

        if relation_i == -1:
            raise ValueError("relation not found!")

        relation_col_name = f"ref_{relation_i}"

        curr_events = self.to_dataframe(raw_cols=True, show_deleted=True)
        joined_events = eventstream.to_dataframe(raw_cols=True, show_deleted=True)
        not_related_events = joined_events[joined_events[relation_col_name].isna()]
        not_related_events_ids = not_related_events[self.schema.event_id]

        merged_events = pd.merge(
            curr_events,
            joined_events,
            left_on=self.schema.event_id,
            right_on=relation_col_name,
            how="outer",
            indicator=True,
        )

        left_id_colname = f"{self.schema.event_id}_y"

        both_events = merged_events[(merged_events["_merge"] == "both")]
        left_events = merged_events[(merged_events["_merge"] == "left_only")]
        right_events = merged_events[
            (merged_events["_merge"] == "both") | (merged_events[left_id_colname].isin(not_related_events_ids))
        ]

        left_raw_cols = self.get_raw_cols()
        right_raw_cols = eventstream.get_raw_cols()
        cols = self._get_both_cols(eventstream)

        result_left_part = pd.DataFrame()
        result_right_part = pd.DataFrame()
        result_deleted_events = pd.DataFrame()

        for col in cols:
            result_left_part[col] = get_merged_col(df=left_events, colname=col, suffix="_x")
            result_deleted_events[col] = get_merged_col(df=both_events, colname=col, suffix="_x")
            result_right_part[col] = get_merged_col(df=right_events, colname=col, suffix="_y")

        for col in left_raw_cols:
            result_left_part[col] = get_merged_col(df=left_events, colname=col, suffix="_x")
            result_deleted_events[col] = get_merged_col(df=both_events, colname=col, suffix="_x")

        for col in right_raw_cols:
            result_right_part[col] = get_merged_col(df=right_events, colname=col, suffix="_y")

        result_left_part[DELETE_COL_NAME] = get_merged_col(df=left_events, colname=DELETE_COL_NAME, suffix="_x")

        result_deleted_events[DELETE_COL_NAME] = True

        left_delete_col = f"{DELETE_COL_NAME}_x"
        right_delete_col = f"{DELETE_COL_NAME}_y"
        result_right_part[DELETE_COL_NAME] = right_events[left_delete_col] | right_events[right_delete_col]

        self.__events = pd.concat([result_left_part, result_right_part, result_deleted_events])
        self.schema.custom_cols = self._get_both_custom_cols(eventstream)
        self.index_events()

    def _get_both_custom_cols(self, eventstream: Eventstream) -> list[str]:
        self_custom_cols = set(self.schema.custom_cols)
        eventstream_custom_cols = set(eventstream.schema.custom_cols)
        all_custom_cols = self_custom_cols.union(eventstream_custom_cols)
        return list(all_custom_cols)

    def _get_both_cols(self, eventstream: Eventstream) -> list[str]:
        self_cols = set(self.schema.get_cols())
        eventstream_cols = set(eventstream.schema.get_cols())
        all_cols = self_cols.union(eventstream_cols)
        return list(all_cols)

    def to_dataframe(self, raw_cols: bool = False, show_deleted: bool = False, copy: bool = False) -> pd.DataFrame:
        cols = self.schema.get_cols() + self.get_relation_cols()

        if raw_cols:
            cols += self.get_raw_cols()

        if show_deleted:
            cols.append(DELETE_COL_NAME)

        events = self.__events if show_deleted else self.__get_not_deleted_events()
        view = pd.DataFrame(events, columns=cols, copy=copy)
        return view

    def index_events(self) -> None:
        order_temp_col_name = "order"
        indexed = self.__events

        indexed[order_temp_col_name] = indexed[self.schema.event_type].apply(lambda e: self.__get_event_priority(e))
        indexed = indexed.sort_values([self.schema.event_timestamp, order_temp_col_name])  # type: ignore
        indexed = indexed.drop([order_temp_col_name], axis=1)
        # indexed[id_col_col_name] = range(1, len(indexed) + 1)
        indexed.reset_index(inplace=True, drop=True)
        indexed[self.schema.event_index] = indexed.index
        self.__events = indexed

    def get_raw_cols(self) -> list[str]:
        cols = self.__events.columns
        raw_cols: list[str] = []
        for col in cols:
            if col.startswith(RAW_COL_PREFIX):
                raw_cols.append(col)
        return raw_cols

    def get_relation_cols(self) -> list[str]:
        cols = self.__events.columns
        relation_cols: list[str] = []
        for col in cols:
            if col.startswith("ref_"):
                relation_cols.append(col)
        return relation_cols

    def add_custom_col(self, name: str, data: pd.Series[Any] | None) -> None:
        self.__raw_data_schema.custom_cols.extend([{"custom_col": name, "raw_data_col": name}])
        self.schema.custom_cols.extend([name])
        self.__events[name] = data

    def soft_delete(self, events: pd.DataFrame) -> None:
        """
        method deletes events either by event_id or by the last relation
        :param events:
        :return:
        """
        deleted_events = events.copy()
        deleted_events[DELETE_COL_NAME] = True
        merged = pd.merge(
            left=self.__events,
            right=deleted_events,
            left_on=self.schema.event_id,
            right_on=self.schema.event_id,
            indicator=True,
            how="left",
        )
        if relation_cols := self.get_relation_cols():
            last_relation_col = relation_cols[-1]
            self.__events[DELETE_COL_NAME] = self.__events[DELETE_COL_NAME] | merged[f"{DELETE_COL_NAME}_y"] == True
            merged = pd.merge(
                left=self.__events,
                right=deleted_events,
                left_on=last_relation_col,
                right_on=self.schema.event_id,
                indicator=True,
                how="left",
            )

        self.__events[DELETE_COL_NAME] = self.__events[DELETE_COL_NAME] | merged[f"{DELETE_COL_NAME}_y"] == True

    def __get_not_deleted_events(self) -> pd.DataFrame | pd.Series[Any]:
        events = self.__events
        return events[events[DELETE_COL_NAME] == False]

    def __prepare_events(self, raw_data: pd.DataFrame | pd.Series[Any]) -> pd.DataFrame | pd.Series[Any]:
        events = raw_data.copy()
        # add "raw_" prefix for raw cols
        events.rename(lambda col: f"raw_{col}", axis="columns", inplace=True)

        events[DELETE_COL_NAME] = False
        events[self.schema.event_id] = [uuid.uuid4() for x in range(len(events))]
        events[self.schema.event_name] = self.__get_col_from_raw_data(
            raw_data=raw_data,
            colname=self.__raw_data_schema.event_name,
        )
        events[self.schema.event_timestamp] = pd.to_datetime(
            self.__get_col_from_raw_data(
                raw_data=raw_data,
                colname=self.__raw_data_schema.event_timestamp,
            ),
        )
        events[self.schema.user_id] = self.__get_col_from_raw_data(
            raw_data=raw_data,
            colname=self.__raw_data_schema.user_id,
        )

        if self.__raw_data_schema.event_type is not None:
            events[self.schema.event_type] = self.__get_col_from_raw_data(
                raw_data=raw_data,
                colname=self.__raw_data_schema.event_type,
            )
        else:
            events[self.schema.event_type] = "raw"

        for custom_col_schema in self.__raw_data_schema.custom_cols:
            raw_data_col = custom_col_schema["raw_data_col"]
            custom_col = custom_col_schema["custom_col"]
            if custom_col not in self.schema.custom_cols:
                self.schema.custom_cols.append(custom_col)

            events[custom_col] = self.__get_col_from_raw_data(
                raw_data=raw_data,
                colname=raw_data_col,
            )

        for custom_col in self.schema.custom_cols:
            if custom_col in events.columns:
                continue
            events[custom_col] = np.nan

        # add relations
        for i in range(len(self.relations)):
            rel_col_name = f"ref_{i}"
            relation = self.relations[i]
            col = raw_data[relation["raw_col"]] if relation["raw_col"] is not None else np.nan
            events[rel_col_name] = col

        return events

    def __get_col_from_raw_data(
        self, raw_data: pd.DataFrame | pd.Series[Any], colname: str, create: bool = False
    ) -> pd.Series | float:
        if colname in raw_data.columns:
            return raw_data[colname]
        else:
            if create:
                return np.nan
            else:
                raise ValueError(f'invalid raw data. Column "{colname}" does not exists!')

    def __get_event_priority(self, event_type: Optional[str]) -> int:
        if event_type in self.index_order:
            return self.index_order.index(event_type)
        return len(self.index_order)

    def __sample_user_paths(
        self,
        raw_data: pd.DataFrame | pd.Series[Any],
        raw_data_schema: RawDataSchemaType,
        user_sample_size: Optional[int | float] = None,
        user_sample_seed: Optional[int] = None,
    ) -> pd.DataFrame | pd.Series[Any]:
        if type(user_sample_size) is not float and type(user_sample_size) is not int:
            raise TypeError('"user_sample_size" has to be a number(float for user share or int for user amount)')
        if user_sample_size < 0:
            raise ValueError("User sample size/share cannot be negative!")
        if type(user_sample_size) is float:
            if user_sample_size > 1:
                raise ValueError("User sample share cannot exceed 1!")
        user_col_name = raw_data_schema.user_id
        unique_users = raw_data[user_col_name].unique()
        if type(user_sample_size) is int:
            sample_size = user_sample_size
        elif type(user_sample_size) is float:
            sample_size = int(user_sample_size * len(unique_users))
        else:
            return raw_data
        if user_sample_seed is not None:
            np.random.seed(user_sample_seed)
        sample_users = np.random.choice(unique_users, sample_size, replace=False)
        raw_data_sampled = raw_data.loc[raw_data[user_col_name].isin(sample_users), :]  # type: ignore
        return raw_data_sampled

    def funnel(
        self,
        stages: list[str],
        stage_names: list[str] | None = None,
        funnel_type: Literal["open", "closed"] = "open",
        segments: Collection[Collection[int]] | None = None,
        segment_names: list[str] | None = None,
        sequence: bool = False,
        show_plot: bool = True,
    ) -> Funnel:

        """
        Shows a visualization of the user sequential events represented as a funnel.

        See parameters description :py:func:`src.tooling.funnel.funnel`

        Returns
        -------
        Funnel
            A ``Funnel`` class instance fitted to the given parameters.

        """
        self.__funnel = Funnel(
            eventstream=self,
            stages=stages,
            stage_names=stage_names,
            funnel_type=funnel_type,
            segments=segments,
            segment_names=segment_names,
            sequence=sequence,
        )
        self.__funnel.fit()
        if show_plot:
            figure = self.__funnel.plot()
            figure.show()
        return self.__funnel

    @property
    def clusters(self) -> Clusters:
        """
        Returns an instance of ``Cluster`` class to be used for cluster analysis.

        See :py:func:`src.tooling.clusters.clusters`

        Returns
        -------
        Clusters
        """
        if self.__clusters is None:
            self.__clusters = Clusters(eventstream=self)
        return self.__clusters

    def step_matrix(
        self,
        max_steps: int = 20,
        weight_col: Optional[str] = None,
        precision: int = 2,
        targets: Optional[list[str] | str] = None,
        accumulated: Optional[Union[Literal["both", "only"], None]] = None,
        sorting: Optional[list[str]] = None,
        thresh: float = 0,
        centered: Optional[dict] = None,
        groups: Optional[Tuple[list, list]] = None,
        show_plot: bool = True,
    ) -> StepMatrix:
        """
        Shows a heatmap visualization of the step matrix.

        See parameters description :py:func:`src.tooling.step_matrix.step_matrix`

        Returns
        -------
        StepMatrix
            A ``StepMatrix`` class instance fitted to the given parameters.

        """
        self.__step_matrix = StepMatrix(
            eventstream=self,
            max_steps=max_steps,
            weight_col=weight_col,
            precision=precision,
            targets=targets,
            accumulated=accumulated,
            sorting=sorting,
            thresh=thresh,
            centered=centered,
            groups=groups,
        )

        self.__step_matrix.fit()
        if show_plot:
            figure = self.__step_matrix.plot()
            figure.show()
        return self.__step_matrix

    def step_sankey(
        self,
        max_steps: int = 10,
        thresh: Union[int, float] = 0.05,
        sorting: list | None = None,
        target: Union[list[str], str] | None = None,
        autosize: bool = True,
        width: int | None = None,
        height: int | None = None,
        show_plot: bool = True,
    ) -> StepSankey:
        """
        Shows a Sankey diagram visualizing the user paths in step-wise manner.

        See parameters description :py:func:`src.tooling.step_sankey.step_sankey`

        Returns
        -------
        StepSankey
            A ``StepSankey`` class instance fitted to the given parameters.

        """
        self.__sankey = StepSankey(
            eventstream=self,
            max_steps=max_steps,
            thresh=thresh,
            sorting=sorting,
            target=target,
            autosize=autosize,
            width=width,
            height=height,
        )

        self.__sankey.fit()
        if show_plot:
            figure = self.__sankey.plot()
            figure.show()
        return self.__sankey

    def cohorts(
        self,
        cohort_start_unit: DATETIME_UNITS,
        cohort_period: Tuple[int, DATETIME_UNITS],
        average: bool = True,
        cut_bottom: int = 0,
        cut_right: int = 0,
        cut_diagonal: int = 0,
        figsize: Tuple[float, float] = (10, 10),
        show_plot: bool = True,
    ) -> Cohorts:

        """
        Shows a heatmap visualization of the user appearance grouped by cohorts.

        See parameters description :py:func:`src.tooling.cohorts.cohorts`

        Returns
        -------
        Cohorts
            A ``Cohorts`` class instance fitted to the given parameters.
        """

        self.__cohorts = Cohorts(
            eventstream=self,
            cohort_start_unit=cohort_start_unit,
            cohort_period=cohort_period,
            average=average,
            cut_bottom=cut_bottom,
            cut_right=cut_right,
            cut_diagonal=cut_diagonal,
        )

        self.__cohorts.fit()
        if show_plot:
            self.__cohorts.heatmap(figsize)
        return self.__cohorts

    def stattest(
        self,
        test: TEST_NAMES,
        groups: Tuple[list[str | int], list[str | int]],
        function: Callable,
        group_names: Tuple[str, str] = ("group_1", "group_2"),
        alpha: float = 0.05,
    ) -> StatTests:
        """
        Determines the statistical difference between the metric values in two user groups.

        See parameters description :py:func:`src.tooling.stattests.stattests`

        Returns
        -------
        StatTests
            A ``StatTest`` class instance fitted to the given parameters.
        """
        self.__stattests = StatTests(
            eventstream=self, groups=groups, func=function, test=test, group_names=group_names, alpha=alpha
        )
        self.__stattests.fit()
        values = self.__stattests.values
        str_template = "{0} (mean ± SD): {1:.3f} ± {2:.3f}, n = {3}"

        print(
            str_template.format(
                values["group_one_name"], values["group_one_mean"], values["group_one_std"], values["group_one_size"]
            )
        )
        print(
            str_template.format(
                values["group_two_name"], values["group_two_mean"], values["group_two_std"], values["group_two_size"]
            )
        )
        print(
            "'{0}' is greater than '{1}' with P-value: {2:.5f}".format(
                values["greatest_group_name"], values["least_group_name"], values["p_val"]
            )
        )
        print("power of the test: {0:.2f}%".format(100 * values["power_estimated"]))

        return self.__stattests

    def timedelta_hist(
        self,
        event_pair: Optional[Tuple[str, str] | List[str]] = None,
        only_adjacent_event_pairs: bool = True,
        weight_col: Optional[str] = None,
        aggregation: Optional[AGGREGATION_NAMES] = None,
        timedelta_unit: DATETIME_UNITS = "s",
        log_scale: bool = False,
        lower_cutoff_quantile: Optional[float] = None,
        upper_cutoff_quantile: Optional[float] = None,
        bins: int = 20,
    ) -> TimedeltaHist:
        self.__timedelta_hist = TimedeltaHist(
            eventstream=self,
            event_pair=event_pair,
            only_adjacent_event_pairs=only_adjacent_event_pairs,
            aggregation=aggregation,
            weight_col=weight_col,
            timedelta_unit=timedelta_unit,
            log_scale=log_scale,
            lower_cutoff_quantile=lower_cutoff_quantile,
            upper_cutoff_quantile=upper_cutoff_quantile,
            bins=bins,
        )
        return self.__timedelta_hist

    def user_lifetime_hist(
        self,
        timedelta_unit: DATETIME_UNITS = "s",
        log_scale: bool = False,
        lower_cutoff_quantile: Optional[float] = None,
        upper_cutoff_quantile: Optional[float] = None,
        bins: int = 20,
    ) -> UserLifetimeHist:
        self.__user_lifetime_hist = UserLifetimeHist(
            eventstream=self,
            timedelta_unit=timedelta_unit,
            log_scale=log_scale,
            lower_cutoff_quantile=lower_cutoff_quantile,
            upper_cutoff_quantile=upper_cutoff_quantile,
            bins=bins,
        )
        return self.__user_lifetime_hist

    def event_timestamp_hist(
        self,
        event_list: Optional[List[str] | str] = 'all',
        lower_cutoff_quantile: Optional[float] = None,
        upper_cutoff_quantile: Optional[float] = None,
        bins: int = 20,
    ) -> SubplotBase:
        if lower_cutoff_quantile is not None:
            if not 0 < lower_cutoff_quantile < 1:
                raise ValueError("lower_cutoff_quantile should be a fraction between 0 and 1.")
        if upper_cutoff_quantile is not None:
            if not 0 < upper_cutoff_quantile < 1:
                raise ValueError("upper_cutoff_quantile should be a fraction between 0 and 1.")

        data = self.to_dataframe()

        if event_list != 'all':
            if type(event_list) is not list:
                raise TypeError('event_list should either be "all", or a list of event names to include.')
            data = data[data[self.schema.event_name].isin(event_list)]

        values = data[self.schema.event_timestamp]
        idx = [True] * len(values)
        if upper_cutoff_quantile is not None:
            idx &= values <= values.quantile(upper_cutoff_quantile)
        if lower_cutoff_quantile is not None:
            idx &= values >= values.quantile(lower_cutoff_quantile)
        return values[idx].hist(bins=bins)

    def describe(self, session_col: Optional[str] = None) -> None:
        user_col, event_col, time_col, type_col = (
            self.schema.user_id,
            self.schema.event_name,
            self.schema.event_timestamp,
            self.schema.event_type,
        )

        df = self.to_dataframe()

        df = df[df[type_col].isin(["raw"])]
        max_time = df[time_col].max()
        min_time = df[time_col].min()

        print(f"\033[1mNumber of unique users:\033[0m {df[user_col].nunique()}")
        print()
        print(f"\033[1mNumber of unique events:\033[0m {df[event_col].nunique()}")
        print()
        print(f"\033[1mStart observations:\033[0m {df[time_col].min()}")
        print()
        print(f"\033[1mEnd observations:\033[0m {df[time_col].max()}")
        print()
        print(f"\033[1mLength of observations (full dataset):\033[0m {max_time  - min_time}")
        print()

        gr_check = df.groupby(user_col).agg({time_col: ["min", "max"], event_col: ["count"]}).reset_index()

        time_diff = gr_check[(time_col, "max")] - gr_check[(time_col, "min")]

        # time users
        mean_time = time_diff.mean()
        median_time = time_diff.median()
        std_time = time_diff.std()
        min_length_time = time_diff.min()
        max_length_time = time_diff.max()

        print('----------------------------------------------------------------------------')
        print("\033[1mTime\033[0m")
        print()
        print(f"\033[1mMean user path length, std (time):\033[0m {mean_time}, {std_time}")
        print()
        print(f"\033[1mMedian user path length (time):\033[0m {median_time}")
        print()
        print(f"\033[1mMin user path length (time):\033[0m {min_length_time}")
        print()
        print(f"\033[1mMax user path length (time):\033[0m {max_length_time}")
        print()

        # events
        event_count = gr_check[(event_col, "count")]
        mean = round(event_count.mean(), 2)  # type: ignore
        median = event_count.median()
        std = round(event_count.std(), 2)  # type: ignore
        min_length = event_count.min()
        max_length = event_count.max()

        print('----------------------------------------------------------------------------')
        print("\033[1mNumber of events\033[0m")
        print()
        print(f"\033[1mMean user path length, std (events):\033[0m {mean}, {std}")
        print()
        print(f"\033[1mMedian user path length (events):\033[0m {median}")
        print()
        print(f"\033[1mMin user path length (events):\033[0m {min_length}")
        print()
        print(f"\033[1mMax user path length (events):\033[0m {max_length}")
        print()

        # sessions
        if session_col:
            print('----------------------------------------------------------------------------')
            df = df.to_dataframe()

            cross = df[df[type_col].isin(["session_start", "session_end"])]
            if len(cross) == 0:
                logging.warning(
                    f"There are no events with types start_session or end_session. \
                    Use the SplitSessions dataprocessor first"
                )

            cross_ = pd.crosstab([cross[user_col], cross[session_col]], cross[type_col]).reset_index()
            cross_["diff"] = cross_["session_end"] - cross_["session_start"]

            full_sessions = cross_[cross_["diff"] == 0][session_col].nunique()

            left_sessions = cross_[cross_["diff"] > 0][session_col].nunique()
            right_sessions = cross_[cross_["diff"] < 0][session_col].nunique()

            print(f"\033[1mNumber of full sessions:\033[0m {full_sessions}")
            print()

            print(f"\033[1mNumber of left_cut sessions:\033[0m {left_sessions}")
            print()
            print(f"\033[1mNumber of right_cut sessions:\033[0m {right_sessions}")

    def describe_events(self) -> None:
        user_col, event_col, time_col, type_col = (
            self.schema.user_id,
            self.schema.event_name,
            self.schema.event_timestamp,
            self.schema.event_type,
        )
        df = self.to_dataframe()
        df['__event_trajectory_idx'] = df.groupby(user_col).cumcount()
        df['__event_trajectory_timedelta'] = df[time_col] - df.groupby(user_col)[time_col].transform('first')
        total_events = df.shape[0]
        unique_users = df[user_col].nunique()

        for i, event_name in enumerate(df[event_col].unique()):
            if i != 0:
                print('============================================================================')
                print()

            event_data = df[df[event_col] == event_name]

            print(f'\033[1m"{event_name}" event statistics:\033[0m')
            print()

            event_share = round(event_data.shape[0] / total_events, 4)
            print(f"\033[1mNumber of observations:\033[0m {event_data.shape[0]}")
            print()
            print(f"\033[1mShare of all events:\033[0m {event_share * 100}%")
            print()

            unique_users_event = event_data[user_col].nunique()
            user_event_share = round(unique_users_event / unique_users, 4)
            print(f"\033[1mNumber of unique users with the event:\033[0m {unique_users_event}")
            print()
            print(f"\033[1mShare of users with the event:\033[0m {user_event_share * 100}%")
            print()

            print('----------------------------------------------------------------------------')
            print("\033[1mAppearances per user path\033[0m")
            print()

            gr_check = event_data.groupby(user_col)[event_col].agg("count")
            mean_events, std_events, median_events = gr_check.mean(), gr_check.std(), gr_check.median()
            min_events, max_events = gr_check.min(), gr_check.max()
            print(f"\033[1mMean appearances per user, std:\033[0m {mean_events}, {std_events}")
            print()
            print(f"\033[1mMedian appearances per user:\033[0m {median_events}")
            print()
            print(f"\033[1mMin appearances per user:\033[0m {min_events}")
            print()
            print(f"\033[1mMax appearances per user:\033[0m {max_events}")
            print()

            print(f"\033[1mFirst appearance:\033[0m {event_data[time_col].min()}")
            print()
            print(f"\033[1mLast appearance:\033[0m {event_data[time_col].max()}")
            print()

            print('----------------------------------------------------------------------------')
            print("\033[1mTime/events since user path start before first appearance\033[0m")
            print()

            gr_check = event_data.groupby(user_col)['__event_trajectory_timedelta'].min()
            mean_time, std_time, median_time = gr_check.mean(), gr_check.std(), gr_check.median()
            min_time, max_time = gr_check.min(), gr_check.max()
            print(f"\033[1mMean user time before first appearance, std:\033[0m {mean_time}, {std_time}")
            print()
            print(f"\033[1mMedian user time before first appearance:\033[0m {median_time}")
            print()
            print(f"\033[1mMin user time before first appearance:\033[0m {min_time}")
            print()
            print(f"\033[1mMax user time before first appearance:\033[0m {max_time}")
            print()

            gr_check = event_data.groupby(user_col)['__event_trajectory_idx'].min()
            mean_events, std_events, median_events = gr_check.mean(), gr_check.std(), gr_check.median()
            min_events, max_events = gr_check.min(), gr_check.max()
            print(f"\033[1mMean user events before first appearance, std:\033[0m {mean_events}, {std_events}")
            print()
            print(f"\033[1mMedian user events before first appearance:\033[0m {median_events}")
            print()
            print(f"\033[1mMin user events before first appearance:\033[0m {min_events}")
            print()
            print(f"\033[1mMax user events before first appearance:\033[0m {max_events}")
            print()




