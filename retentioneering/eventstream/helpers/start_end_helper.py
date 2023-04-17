from __future__ import annotations

from ..types import EventstreamType


class StartEndHelperMixin:
    def add_start_end(self) -> EventstreamType:
        """
        A method of ``Eventstream`` class that creates
        two synthetic events in each user's path: ``path_start`` and ``path_end``.

        Returns
        -------
        Eventstream
            Input ``eventstream`` with added synthetic events. See details :py:class:`.StartEndEvents`.


        """
        # avoid circular import
        from retentioneering.data_processors_lib import (
            StartEndEvents,
            StartEndEventsParams,
        )
        from retentioneering.preprocessing_graph.nodes import EventsNode
        from retentioneering.preprocessing_graph.preprocessing_graph import (
            PreprocessingGraph,
        )

        p = PreprocessingGraph(source_stream=self)  # type: ignore

        node = EventsNode(processor=StartEndEvents(params=StartEndEventsParams(**{})))
        p.add_node(node=node, parents=[p.root])
        result = p.combine(node)
        del p
        return result
