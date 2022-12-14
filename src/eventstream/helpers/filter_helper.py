from __future__ import annotations

from typing import Any, Callable

from pandas import DataFrame

from ..types import EventstreamSchemaType, EventstreamType


class FilterHelperMixin:
    def filter(self, filter: Callable[[DataFrame, EventstreamSchemaType], Any]) -> EventstreamType:
        """
        Method of ``Eventstream Class`` which filters input ``eventstream`` on the basis of custom conditions.

        Returns
        -------
        EventstreamType
            Filtered ``eventstream``.

        See Also
        --------
        :py:func:`src.data_processors_lib.rete.filter_events.FilterEvents`
        """
        # avoid circular import
        from src.data_processors_lib.rete import FilterEvents, FilterEventsParams
        from src.graph.nodes import EventsNode
        from src.graph.p_graph import PGraph

        p = PGraph(source_stream=self)  # type: ignore

        node = EventsNode(processor=FilterEvents(params=FilterEventsParams(filter=filter)))  # type: ignore
        p.add_node(node=node, parents=[p.root])
        result = p.combine(node)
        del p
        return result
