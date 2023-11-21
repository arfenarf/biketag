import geopandas as gpd
import pandas as pd
import branca.colormap as cm
import folium
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


def create_person_df(cluster_filepath, gdf, sep=","):
    person_df = pd.concat(
        [
            gdf[["placed_by", "geometry"]].rename(columns={"placed_by": "person"}),
            gdf[["found_by", "geometry"]].rename(columns={"found_by": "person"}),
        ]
    )
    person_df["location_count"] = 1
    # and now we roll it up
    person_df = person_df.dissolve(by="person", aggfunc="count")

    # graft in some graph smartness
    cluster_info = pd.read_csv(cluster_filepath, sep=sep)
    person_df = person_df.join(
        cluster_info[["Label", "modularity_class"]].set_index("Label")
    )
    person_df.modularity_class = person_df.modularity_class.astype("category")
    person_df = person_df.rename(columns={"modularity_class": "cluster"})

    # print(person_df.head())

    # add the convex and concave hulls
    person_df["convex_hull"] = person_df.geometry.convex_hull
    person_df["concave_hull"] = person_df.geometry.concave_hull()

    # force an area calculation in square miles
    person_df["convex_hull_area"] = (
        person_df.convex_hull.to_crs("+proj=cea").area * 3.861e-7
    )
    person_df["location_density"] = (
        person_df.location_count / person_df.convex_hull_area
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


def create_mapping_df(person_df):
    mapping_df = (
        person_df.loc[person_df.location_count > 2]
        .reset_index()
        .set_geometry("convex_hull")
        .sort_values(by="convex_hull_area", ascending=False)
    )
    return mapping_df


def build_map(map_df, person_df, gdf, person_subset=None):
    person_subset = (
        list(map_df.person.unique()) if person_subset is None else person_subset
    )
    map_df = map_df.loc[map_df.person.isin(person_subset)]

    colors = cm.linear.Set1_08.to_step(n=person_df.person_id.max()).scale(
        0, person_df.person_id.max()
    )
    map_df["__color"] = map_df.person_id.apply(colors)

    # create the map object
    m = folium.Map(
        location=[42.3312832, -83.79662475],
        zoom_start=11,
        tiles="https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=5d38772f44bf4755bd8859e5bf9ef4a5",
        attr='&copy; <a href="http://www.thunderforest.com/">Thunderforest</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    )

    # add the hull shapes
    folium.GeoJson(
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
        style_function=lambda x: {
            "fillColor": x["properties"]["__color"],
            "color": "grey",
            "weight": 1,
            "fillOpacity": 0.3,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["person", "cluster", "convex_hull_area", "location_density"],
            aliases=["Person Name", "cluster", "Area (sq. mi.)", "Tags/mi^2"],
        ),
    ).add_to(m)

    # add the tag locations
    folium.GeoJson(
        gdf,
        name="Tags Placed",
        marker=folium.CircleMarker(
            radius=5, fill_color="blue", fill_opacity=0.3, color="black", weight=1
        ),
        tooltip=folium.GeoJsonTooltip(
            fields=["name", "placed_by", "found_by"],
            aliases=["Location Name", "Placed By", "Found By"],
        ),
        popup=folium.GeoJsonPopup(
            fields=["name", "placed_by", "found_by"],
            aliases=["Location Name", "Placed By", "Found By"],
        ),
        style_function=lambda x: {
            "fillColor": colors(x["properties"]["placed_by_id"]),
        },
    ).add_to(m)

    m.save("templates/biketag.html")
    return m


def load_and_build_map(biketag_filepath, cluster_filepath):
    gdf = load_data(biketag_filepath)
    person_df = create_person_df(cluster_filepath, gdf)
    gdf = merge_person_data(gdf, person_df)
    map_df = create_mapping_df(person_df)
    m = build_map(map_df, person_df, gdf)
    # load_table(person_df)
    return m, map_df, person_df, gdf


if __name__ == "__main__":
    load_and_build_map("data/biketag.tsv", "data/person_nodes.csv")
