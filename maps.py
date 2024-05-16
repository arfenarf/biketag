import branca.colormap as cm
import community as community_louvain
import folium
import geopandas as gpd
import networkx as nx
import pandas as pd
import requests


def load_data(filepath="data/biketag.tsv", sep="\t"):
    """Load the bike-tag data from a TSV copy of the Google Sheet"""
    r = requests.get(
        "https://docs.google.com/spreadsheets/d/1ngFLRbIZAnWOyczNyph2WIQlysRoTJC2kkPqgNCpkoE/export?format=tsv"
    )

    with open(filepath, "w") as f:
        f.write(r.text)

    biketag = pd.read_csv(filepath, sep=sep, encoding="utf-8")
    gdf = gpd.GeoDataFrame(
        biketag,
        geometry=gpd.points_from_xy(biketag.longitude, biketag.latitude),
        crs="EPSG:4326",
    )
    return gdf


def create_person_df(gdf):
    person_df = pd.concat(
        [
            gdf[["placed_by", "geometry"]].rename(columns={"placed_by": "person"}),
            gdf[["found_by", "geometry"]].rename(columns={"found_by": "person"}),
        ]
    )
    person_df["location_count"] = 1
    # and now we roll it up
    person_df = person_df.dissolve(by="person", aggfunc="count")

    # add the convex and concave hulls
    person_df["convex_hull"] = person_df.geometry.convex_hull
    person_df["concave_hull"] = person_df.geometry.concave_hull()

    # let's get the center of the convex hull
    person_df["convex_hull_center"] = person_df.convex_hull.to_crs("+proj=cea").centroid

    # force an area calculation in square miles
    person_df["convex_hull_area"] = (
        person_df.convex_hull.to_crs("+proj=cea").area * 3.861e-7
    )
    person_df["location_density"] = person_df.apply(
        lambda row: row.location_count / row.convex_hull_area
        if row.convex_hull_area > 0
        else 0,
        axis=1,
    )
    person_df["person_id"] = range(len(person_df))

    return person_df


def merge_person_data(gdf, person_df):
    gdf = gdf.merge(
        person_df[["person_id"]], left_on="placed_by", right_index=True
    ).rename(columns={"person_id": "placed_by_id"})
    gdf = gdf.merge(
        person_df[["person_id"]], left_on="found_by", right_index=True
    ).rename(columns={"person_id": "found_by_id"})
    return gdf


def cluster_people(gdf, person_df):
    # create a networkx graph
    G = nx.Graph()

    # add the edges
    for index, row in gdf.iterrows():
        G.add_edge(row.placed_by_id, row.found_by_id)

    # run the clustering algorithm
    partition = community_louvain.best_partition(G, random_state=42)
    person_df["cluster"] = person_df.person_id.apply(lambda x: partition[x])
    person_df["cluster_label"] = person_df.cluster.apply(lambda x: f"C-{x}")

    return person_df, {"graph": G, "partition": partition}


def create_mapping_df(person_df):
    mapping_df = (
        person_df.loc[person_df.location_count > 2]
        .reset_index()
        .set_geometry("convex_hull")
        .sort_values(by="convex_hull_area", ascending=False)
    )
    return mapping_df


def build_map(map_df, person_df, gdf, clusters):
    step = cm.linear.Set1_08.to_step(clusters).scale(0, 5)
    map_df["__color"] = map_df.cluster.apply(step)

    # create the map object
    m = folium.Map(location=[42.3312832, -83.79662475], zoom_start=11, tiles=None)

    folium.TileLayer(
        name="OpenCycleMap",
        tiles="https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=5d38772f44bf4755bd8859e5bf9ef4a5",
        attr='&copy; <a href="http://www.thunderforest.com/">Thunderforest</a>, &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
        overlay=False,
        control=True,
    ).add_to(m)

    # add the hull shapes
    h = folium.GeoJson(
        map_df[
            [
                "person",
                "convex_hull",
                "convex_hull_area",
                "cluster",
                "location_density",
                "__color",
            ]
        ],
        name="Rider Coverage Area",
        style_function=lambda x: {
            "fillColor": x["properties"]["__color"],
            "color": "grey",
            "weight": 1,
            "fillOpacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["person", "cluster", "convex_hull_area", "location_density"],
            aliases=["Person Name", "cluster", "Area (sq. mi.)", "Tags/mi^2"],
        ),
    )
    h.add_to(m)

    # add the tag locations
    display_gdf = gdf.loc[
        (gdf.placed_by_id.isin(person_df.person_id))
        | (gdf.found_by_id.isin(person_df.person_id))
    ]

    if len(display_gdf) > 0:
        folium.GeoJson(
            display_gdf,
            name="Tags Placed",
            marker=folium.CircleMarker(
                radius=3, fill_color="darkblue", fill_opacity=1, color="grey", weight=1
            ),
            tooltip=folium.GeoJsonTooltip(
                fields=["name", "placed_by", "found_by"],
                aliases=["Location Name", "Placed By", "Found By"],
            ),
            popup=folium.GeoJsonPopup(
                fields=["name", "placed_by", "found_by"],
                aliases=["Location Name", "Placed By", "Found By"],
            ),
        ).add_to(m)

    # add the centroids
    centroid_df = person_df.copy()

    if len(centroid_df) > 0:
        centroid_df = centroid_df.set_geometry("convex_hull_center", drop=True)
        centroid_df = centroid_df[
            ["cluster", "cluster_label", "person_id", "geometry"]
        ].reset_index()
        centroid_df["__color"] = centroid_df.cluster.apply(step)
        z = folium.GeoJson(
            centroid_df,
            name="Centroids",
            marker=folium.CircleMarker(
                radius=6, fill_color="green", fill_opacity=1, color="black", weight=1
            ),
            tooltip=folium.GeoJsonTooltip(
                fields=["person", "cluster_label"],
                aliases=["Centroid for:", "Cluster:"],
            ),
            popup=folium.GeoJsonPopup(
                fields=["person", "cluster_label"],
                aliases=["Centroid for:", "Cluster:"],
            ),
            style_function=lambda x: {
                "fillColor": x["properties"]["__color"],
                "color": "black",
                "weight": 1,
                "fillOpacity": 0.7,
            },
        )

        z.add_to(m)

    folium.LayerControl().add_to(m)
    # m.save("assets/biketag.html")
    return m


def load_and_build_map(biketag_filepath):
    gdf = load_data(biketag_filepath)
    person_df = create_person_df(gdf)
    gdf = merge_person_data(gdf, person_df)
    person_df, _ = cluster_people(gdf, person_df)
    clusters = len(person_df.cluster.unique())
    map_df = create_mapping_df(person_df)
    m = build_map(map_df, person_df, gdf, clusters)
    return m, map_df, person_df, gdf


if __name__ == "__main__":
    load_and_build_map("data/biketag.tsv")
