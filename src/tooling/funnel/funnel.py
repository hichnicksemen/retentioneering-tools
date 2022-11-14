from __future__ import annotations

from collections.abc import Collection
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
from pandas.core.common import flatten

from src.eventstream.types import EventstreamType


class Funnel:
    """
    Plots conversion funnel with specified parameters.

    Parameters
    ----------
    stages: list of str
        List of events used as stages for the funnel. Absolute and relative
        number of users who reached specified events at least once will be
        plotted. Multiple events can be grouped together as individual state
        by combining them as sub list.
    stage_names: list of str | None (default None)
        List of stage names, this is especially necessary for stages that include several events.
    funnel_type: 'open' or 'closed' (optional, default 'open')
        if ``open`` - all users will be counted on each stage.
        if ``closed`` - Each stage will include only users, who was on all previous stages.
    segments: Collection[Collection[int]] | None (default None)
        List of user_ids collections. Funnel for each user_id collection will be plotted.
        If ``None`` - all users from dataset will be plotted. A user can only belong to one segment at a time.
    segment_names: list of strings | None (default None)
        Names of segments. Should be a list from unique values of the ``segment_col``.
        If ``None`` and ``segment_col`` is given - all values from ``segment_col`` will be used.
    sequence: Boolean (default False)
        Used for closed funnels only
        If ``True``, the sequence and timestamp of events is taken into account when constructing the funnel.
        In another case, the standard closed funnel rules will be implemented.

    See Also
    --------
    :py:func:`src.eventstream.funnel`

    """

    __eventstream: EventstreamType
    __default_layout = dict(
        margin={"l": 180, "r": 0, "t": 30, "b": 0, "pad": 0},
        funnelmode="stack",
        showlegend=True,
        hovermode="closest",
        legend=dict(orientation="v", bgcolor="#E2E2E2", xanchor="left", font=dict(size=12)),
    )

    def __init__(
        self,
        eventstream: EventstreamType,
        stages: list[str],
        stage_names: list[str] | None = None,
        funnel_type: Literal["open", "closed"] = "open",
        segments: Collection[Collection[int]] | None = None,
        segment_names: list[str] | None = None,
        sequence: bool = False,
    ) -> None:
        self.__eventstream = eventstream
        self.user_col = self.__eventstream.schema.user_id
        self.event_col = self.__eventstream.schema.event_name
        self.time_col = self.__eventstream.schema.event_timestamp
        self.stages = stages
        self.stage_names = stage_names
        self.funnel_type: Literal["open", "closed"] = funnel_type
        self.sequence = sequence

        data = self.__eventstream.to_dataframe()
        data = data[data[self.event_col].isin([i for i in flatten(stages)])]  # type: ignore
        self.data = data

        if self.stages and self.stage_names and len(self.stages) != len(self.stage_names):
            raise ValueError("stages and stage_names must be the same length!")

        if segments is None:
            segments = [self.data[self.user_col].unique().tolist()]
            segment_names = ["all users"]
        else:
            sets = [set(segment) for segment in segments]
            if len(set.intersection(*sets)) > 0:
                raise ValueError("Check intersections of users in segments!")

        if segment_names is None:
            segment_names = [f"group {i}" for i in range(len(segments))]  # type: ignore

        if segments and segment_names and len(segments) != len(segment_names):  # type: ignore
            raise ValueError("segments and segment_names must be the same length!")

        # IDK why but pyright thinks this is Funnel!!!
        self.segments = segments
        self.segment_names = segment_names

        if funnel_type not in ["open", "closed"]:
            raise ValueError("funnel_type should be 'open' or 'closed'!")

    def draw_plot(self) -> go.Figure:
        """

        Returns
        -------
        Funnel plot
        """
        plot_params = self._calculate(
            data=self.data,
            stages=self.stages,
            stage_names=self.stage_names,
            funnel_type=self.funnel_type,
            segments=self.segments,
            segment_names=self.segment_names,
            sequence=self.sequence,
        )
        data = self._calculate_plot_data(plot_params=plot_params)
        plot = self._plot_stacked_funnel(data=data)
        return plot

    def _calculate(
        self,
        data: pd.DataFrame,
        stages: list[str],
        stage_names: list[str] | None,
        funnel_type: Literal["open", "closed"],
        segments: Collection[Collection[int]],
        segment_names: list[str],
        sequence: bool = False,
    ) -> dict[str, Any]:

        res_dict = {}
        for idx, stage in enumerate(stages):
            if type(stage) is not list:
                stages[idx] = [stage]  # type: ignore

        if stage_names is None:
            stage_names = []
            for t in stages:
                # get name
                stage_names.append(" | ".join(t).strip(" | "))

        if funnel_type == "closed":
            res_dict = self._prepare_data_for_closed_funnel(
                data=data,
                stages=stages,
                segments=segments,
                segment_names=segment_names,
                stage_names=stage_names,
                sequence=sequence,
            )

        elif funnel_type == "open":
            res_dict = self._prepare_data_for_open_funnel(
                data=data, stages=stages, segments=segments, segment_names=segment_names, stage_names=stage_names
            )
        return res_dict

    def _plot_stacked_funnel(self, data) -> go.Figure:
        layout = go.Layout(**self.__default_layout)
        fig = go.Figure(data, layout)

        # @TODO: Why do we need to write graph to html?
        # plot_name = 'funnel_plot_{}'.format(datetime.now()).replace(':', '_').replace('.', '_') + '.html'
        # path = f'/home/vladimir/Workspace/retentioneering/retentioneering-tools-new-arch/src/expetiments/{plot_name}'
        # _tmpfile = tempfile.NamedTemporaryFile()
        # path = _tmpfile.name
        # fig.write_html(path)

        return fig

    def _calculate_plot_data(self, plot_params: dict[str, Any]) -> list[go.Funnel]:
        data = []
        for t in plot_params.keys():
            trace = go.Funnel(
                name=t,
                y=plot_params[t]["stages"],
                x=plot_params[t]["values"],
                textinfo="value+percent initial+percent previous",
            )
            data.append(trace)

        return data

    def _prepare_data_for_closed_funnel(
        self,
        data: pd.DataFrame,
        stages: list[str],
        stage_names: list[str],
        segments: Collection[Collection[int]],
        segment_names: list[str],
        sequence: bool = False,
    ):

        min_time_0stage = (
            data[data[self.event_col].isin(stages[0])].groupby(self.user_col)[[self.time_col]].min().reset_index()
        )
        data = data.merge(min_time_0stage, "left", on=self.user_col, suffixes=("", "_min"))
        data.rename(columns={data.columns[-1]: "min_date"}, inplace=True)

        # filtered NA and only events that occured after the user entered the first funnel event remain
        data = data[(~data["min_date"].isna()) & (data["min_date"] <= data[self.time_col])]
        data.drop(columns="min_date", inplace=True)

        res_dict = {}
        for segment, name in zip(segments, segment_names):
            vals, _df = self._crop_df(data, stages, segment, sequence)
            res_dict[name] = {"stages": stage_names, "values": vals}
        return res_dict

    def _prepare_data_for_open_funnel(
        self,
        data: pd.DataFrame,
        stages: list[str],
        stage_names: list[str],
        segments: Collection[Collection[int]],
        segment_names: list[str],
    ):
        res_dict = {}
        for segment, name in zip(segments, segment_names):
            # isolate users from group
            group_data = data[data[self.user_col].isin(segment)]
            vals = [group_data[group_data[self.event_col].isin(stage)][self.user_col].nunique() for stage in stages]
            res_dict[name] = {"stages": stage_names, "values": vals}
        return res_dict

    def _crop_df(self, df: pd.DataFrame, stages: list[str], segment: Collection[int], sequence: bool = False):
        first_stage = stages[0]
        next_stages = stages[1:]

        first_stage_users = set(
            (df[(df[self.event_col].isin(first_stage)) & (df[self.user_col].isin(segment))][self.user_col])
        )
        df = df.drop(
            df[(~df[self.user_col].isin(first_stage_users)) | (df[self.event_col].isin(first_stage))].index.tolist()
        )

        prev_users_stage = first_stage_users
        vals = [len(first_stage_users)]
        for stage in next_stages:
            user_stage = set(
                df[(df[self.event_col].isin(stage)) & (df[self.user_col].isin(first_stage_users))][self.user_col]
            )
            user_stage = user_stage - (user_stage - prev_users_stage)
            prev_users_stage = user_stage

            vals.append(len(user_stage))

            if sequence:
                stage_min_df = (
                    df[df[self.event_col].isin(stage)].groupby(self.user_col)[[self.time_col]].min().reset_index()
                )
                df = df.merge(stage_min_df, "left", on=self.user_col, suffixes=("", "_min"))
                df.rename(columns={df.columns[-1]: "min_date"}, inplace=True)

                df.drop(
                    df[
                        (df["min_date"].isna())
                        | (df["min_date"] >= df[self.time_col])
                        | (~df[self.user_col].isin(user_stage))
                    ].index.tolist(),
                    inplace=True,
                )
                df.drop(columns="min_date", inplace=True)
            else:
                df = df.drop(df[~df[self.user_col].isin(user_stage)].index.tolist())

        return vals, df
