from __future__ import annotations

from typing import Any, List, Literal, Tuple, cast

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import rcParams
from numpy import ndarray
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.mixture import GaussianMixture

from src.eventstream.types import EventstreamType
from src.tooling.clusters.segments import Segments

FeatureType = Literal["tfidf", "count", "frequency", "binary", "time", "time_fraction", "external"]
NgramRange = Tuple[int, int]
Method = Literal["kmeans", "gmm"]
PlotType = Literal["cluster_bar"]


class Clusters:
    __eventstream: EventstreamType
    __clusters_list: list[int] | ndarray
    segments: Segments | None

    def __init__(self, eventstream: EventstreamType, user_clusters: dict[str | int, list[int]] | None = None):
        self.__eventstream = eventstream
        self.segments = None
        self.user_clusters = user_clusters

    def __get_vectorizer(
        self,
        feature_type: Literal["count", "frequency", "tfidf", "binary"],
        ngram_range: NgramRange,
        corpus,
    ) -> TfidfVectorizer | CountVectorizer:
        if feature_type == "tfidf":
            return TfidfVectorizer(ngram_range=ngram_range, token_pattern="[^~]+").fit(corpus)  # type: ignore
        elif feature_type in ["count", "frequency"]:
            return CountVectorizer(ngram_range=ngram_range, token_pattern="[^~]+").fit(corpus)  # type: ignore
        else:
            return CountVectorizer(ngram_range=ngram_range, token_pattern="[^~]+", binary=True).fit(  # type: ignore
                corpus
            )

    def _extract_features(
        self, eventstream: EventstreamType, feature_type: FeatureType = "tfidf", ngram_range: NgramRange | None = None
    ):
        if ngram_range is None:
            ngram_range = (1, 1)
        index_col = eventstream.schema.user_id
        event_col = eventstream.schema.event_id
        time_col = eventstream.schema.event_timestamp

        events = eventstream.to_dataframe()

        corpus = events.groupby(index_col)[event_col].apply(lambda x: "~~".join([el.lower() for el in x]))

        vec_data = None

        if (
            feature_type == "count"
            or feature_type == "frequency"
            or feature_type == "tfidf"
            or feature_type == "binary"
        ):
            vectorizer = self.__get_vectorizer(feature_type=feature_type, ngram_range=ngram_range, corpus=corpus)

            vocabulary_items = sorted(vectorizer.vocabulary_.items(), key=lambda x: x[1])
            cols: list[str] = [dict_key[0] for dict_key in vocabulary_items]
            sorted_index_col = sorted(events[index_col].unique())

            vec_data = pd.DataFrame(index=sorted_index_col, columns=cols, data=vectorizer.transform(corpus).todense())
            vec_data.index.rename(index_col, inplace=True)

            if feature_type == "frequency":
                # TODO: fix me
                sum = cast(Any, vec_data.sum(axis=1))
                vec_data = vec_data.div(sum, axis=0).fillna(0)

        if feature_type in ["time", "time_fraction"]:
            events.sort_values(by=[index_col, time_col], inplace=True)
            events.reset_index(inplace=True)
            events["time_diff"] = events.groupby(index_col)[time_col].diff().dt.total_seconds()  # type: ignore
            events["time_length"] = events["time_diff"].shift(-1)
            if feature_type == "time_fraction":
                vec_data = (
                    events.groupby([index_col])
                    .apply(lambda x: x.groupby(event_col)["time_length"].sum() / x["time_length"].sum())
                    .unstack(fill_value=0)
                )
            elif feature_type == "time":
                vec_data = (
                    events.groupby([index_col])
                    .apply(lambda x: x.groupby(event_col)["time_length"].sum())
                    .unstack(fill_value=0)
                )

        if vec_data is not None:
            vec_data.columns = [col + "_" + feature_type for col in vec_data.columns]

        return cast(pd.DataFrame, vec_data)

    # TODO: add save
    def _cluster_bar(self, clusters: list[int] | ndarray, target: list[list[bool]], target_names: list[str]):
        """
        Plots bar charts with cluster sizes and average target conversion rate.
        Parameters
        ----------
        data : pd.DataFrame
            Feature matrix.
        clusters : "np.array"
            Array of cluster IDs.
        target: "np.array"
            Boolean vector, if ``True``, then user has `positive_target_event` in trajectory.
        target: list[np.ndarray]
            Boolean vector, if ``True``, then user has `positive_target_event` in trajectory.
        kwargs: optional
            Width and height of plot.
        Returns
        -------
        Saves plot to ``retention_config.experiments_folder``
        Return type
        -------
        PNG
        """
        cl = pd.DataFrame([clusters, *target], index=["clusters", *target_names]).T
        cl["cluster size"] = 1
        for t_n in target_names:
            cl[t_n] = cl[t_n].astype(int)

        bars = (
            cl.groupby("clusters").agg({"cluster size": "sum", **{t_n: "mean" for t_n in target_names}}).reset_index()
        )
        bars["cluster size"] /= bars["cluster size"].sum()

        bars = bars.melt("clusters", var_name="type", value_name="value")
        bars = bars[bars["type"] != " "].copy()

        fig_x_size = round((1 + bars["clusters"].nunique() ** 0.7 * bars["type"].nunique() ** 0.7))
        rcParams["figure.figsize"] = fig_x_size, 6

        bar = sns.barplot(x="clusters", y="value", hue="type", data=bars)

        # move legend outside the box
        bar.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.0)

        y_value = ["{:,.2f}".format(x * 100) + "%" for x in bar.get_yticks()]

        bar.set_yticks(bar.get_yticks().tolist())
        bar.set_yticklabels(y_value)
        bar.set(ylabel=None)

        # adjust the limits
        ymin, ymax = bar.get_ylim()
        if ymax > 1:
            bar.set_ylim(ymin, 1.05)

        return bar

    def _kmeans(self, features: pd.DataFrame, n_clusters: int = 8, random_state: int = 0) -> np.ndarray:

        km = KMeans(random_state=random_state, n_clusters=n_clusters)

        cl = km.fit_predict(features.values)

        return cl

    def _gmm(self, features: pd.DataFrame, n_clusters: int = 8, random_state: int = 0) -> np.ndarray:

        km = GaussianMixture(random_state=random_state, n_components=n_clusters)

        cl = km.fit_predict(features.values)

        return cl

    def create_clusters(
        self,
        feature_type: FeatureType = "tfidf",
        ngram_range: NgramRange = (1, 1),
        n_clusters: int = 8,
        method: Method = "kmeans",
        refit_cluster: bool = True,
        targets: list[str] | None = None,
        vector: pd.DataFrame | None = None,
    ):
        if self.user_clusters:
            targets_bool = [[True] * x for x in [len(y) for y in self.user_clusters.values()]]
            target_names: list[str] = list(map(str, list(self.user_clusters.keys())))
        else:
            target_names, targets_bool = self._prepare_clusters(
                feature_type=feature_type,
                method=method,
                n_clusters=n_clusters,
                ngram_range=ngram_range,
                refit_cluster=refit_cluster,
                targets=targets,
                vector=vector,
            )

        return self._cluster_bar(
            clusters=self.__clusters_list,
            target=cast(List[List[bool]], targets_bool),  # TODO: fix types
            target_names=target_names,
        )

    def _prepare_clusters(self, feature_type, method, n_clusters, ngram_range, refit_cluster, targets, vector):
        user_col = self.__eventstream.schema.user_id
        event_col = self.__eventstream.schema.event_id
        if feature_type == "external" and not isinstance(vector, pd.DataFrame):  # type: ignore
            raise ValueError("Vector is not a DataFrame!")
        if feature_type == "external" and vector is not None:
            # Check consistency and copy vector to features
            if np.all(np.all(vector.dtypes == "float") and vector.isna().sum().sum() == 0):
                features = vector.copy()
            else:
                raise ValueError(
                    "Vector is wrong formatted! NaN should be replaced with 0 and dtypes all must be float!"
                )
        else:
            features = self._extract_features(
                eventstream=self.__eventstream,
                feature_type=feature_type,
                ngram_range=ngram_range,
            )
        users_ids: pd.Series = features.index.to_series()
        if self.segments is None or refit_cluster:
            if method == "kmeans":
                clusters_list = self._kmeans(features=features, n_clusters=n_clusters)
            elif method == "gmm":
                clusters_list = self._gmm(
                    features=features,
                    n_clusters=n_clusters,
                )
            else:
                raise ValueError("Unknown method: %s" % method)

            self.__clusters_list = clusters_list

            users_clusters = users_ids.to_frame().reset_index(drop=True)
            users_clusters["segment"] = pd.Series(clusters_list)

            self.segments = Segments(
                eventstream=self.__eventstream,
                segments_df=users_clusters,
            )
        events = self.__eventstream.to_dataframe()
        grouped_events = events.groupby(user_col)[event_col]
        target_names, targets_bool = self._prepare_targets(event_col, grouped_events, targets)
        return target_names, targets_bool

    def _prepare_targets(self, event_col, grouped_events, targets):
        if targets is not None:
            targets_bool = []
            target_names = []

            formated_targets = []
            # format targets to list of lists:
            for n, i in enumerate(targets):
                if type(i) != list:  # type: ignore
                    formated_targets.append([i])
                else:
                    formated_targets.append(i)  # type: ignore

            for t in formated_targets:
                # get name
                target_names.append("CR: " + " ".join(t))
                # get bool vector
                targets_bool.append(
                    (grouped_events.apply(lambda x: bool(set(t) & set(x))).to_frame().sort_index()[event_col].values)
                )

        else:
            targets_bool = [np.array([False] * len(self.__clusters_list))]
            target_names = [" "]
        return target_names, targets_bool
