from __future__ import annotations

from typing import Callable, MutableMapping, MutableSequence

import pandas as pd

from retentioneering.tooling.typing.transition_graph import NormType

NormFunc = Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame], pd.Series]


class Edgelist:
    edgelist_norm_functions: MutableMapping[str, NormFunc] | None
    edgelist_df: pd.DataFrame
    event_col: str
    time_col: str
    default_weight_col: str = "events"
    nodelist: pd.DataFrame
    _index_col: str = ""
    _weight_col: str = ""

    def __init__(
        self,
        event_col: str,
        time_col: str,
        weight_col: str,
        index_col: str,
        nodelist: pd.DataFrame,
        edgelist_norm_functions: MutableMapping[str, NormFunc] | None = None,
    ) -> None:
        self.event_col = event_col
        self.time_col = time_col
        self.nodelist = nodelist
        self.weight_col = weight_col or self.default_weight_col
        self.index_col = index_col
        self.edgelist_norm_functions = edgelist_norm_functions

    @property
    def weight_col(self) -> str:
        return self._weight_col

    @weight_col.setter
    def weight_col(self, value: str) -> None:
        if value == self.index_col:
            raise ValueError("Index column not may be equal to weight column")

        self._weight_col = value

    @property
    def index_col(self) -> str:
        return self._index_col

    @index_col.setter
    def index_col(self, value: str) -> None:
        if value == self.weight_col:
            raise ValueError("Index column not may be equal to weight column")
        self._index_col = value

    def calculate_edgelist(
        self,
        data: pd.DataFrame,
        norm_type: NormType | None = None,
        custom_cols: MutableSequence[str] | None = None,
        custom_weight: str | None = None,
    ) -> pd.DataFrame:

        if norm_type not in [None, "full", "node"]:
            raise ValueError(f"unknown normalization type: {norm_type}")
        if custom_weight is not None:
            self.weight_col = custom_weight

        cols = [self.event_col, f"next_{self.event_col}"]
        data = self._get_shift(data=data, event_col=self.event_col, time_col=self.time_col)

        edgelist = data.groupby(cols)[self.time_col].count().reset_index()
        edgelist.rename(columns={self.time_col: self.weight_col}, inplace=True)

        if custom_cols is not None:
            for weight_col in custom_cols:
                agg_i = data.groupby(cols)[weight_col].nunique().reset_index()
                edgelist = edgelist.join(agg_i[weight_col])

        # apply default norm func
        if norm_type == "full":
            edgelist[self.weight_col] /= edgelist[self.weight_col].sum()
            if custom_cols is not None:
                for weight_col in custom_cols:
                    edgelist[weight_col] /= data[weight_col].nunique()

        elif norm_type == "node":
            event_transitions_counter = data.groupby(self.event_col)[cols[1]].count().to_dict()

            edgelist[self.weight_col] /= edgelist[cols[0]].map(event_transitions_counter)

            if custom_cols is not None:
                for weight_col in custom_cols:
                    user_counter = data.groupby(cols[0])[weight_col].nunique().to_dict()
                    edgelist[weight_col] /= edgelist[cols[0]].map(user_counter)

        # @TODO: подумать над этим (legacy from private by Alexey). Vladimir Makhanov
        # apply custom norm func for event col
        if self.edgelist_norm_functions is not None:
            if self.weight_col in self.edgelist_norm_functions:
                edgelist[self.weight_col] = self.edgelist_norm_functions[self.weight_col](data, self.nodelist, edgelist)

            if custom_cols is not None:
                for weight_col in custom_cols:
                    if weight_col in self.edgelist_norm_functions:
                        edgelist[weight_col] = self.edgelist_norm_functions[weight_col](data, self.nodelist, edgelist)

        self.edgelist_df = edgelist
        return edgelist

    def _get_shift(self, data: pd.DataFrame, event_col: str, time_col: str) -> pd.DataFrame:
        data.sort_values([self.index_col, time_col], inplace=True)
        shift = data.groupby(self.index_col).shift(-1)

        data["next_" + event_col] = shift[event_col]
        data["next_" + str(time_col)] = shift[time_col]

        return data
