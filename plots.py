from bokeh.models import Range1d, Circle, MultiLine
import json

import networkx as nx
import plotly.express as px
import plotly.graph_objects as go
from bokeh.embed import components
from bokeh.models import Range1d, Circle, MultiLine
from bokeh.palettes import Spectral8
from bokeh.plotting import figure
from bokeh.plotting import from_networkx
from plotly.utils import PlotlyJSONEncoder


def create_plotly_distograms(tag_df):
    x0 = tag_df.drive_distance_mi
    x1 = tag_df.crow_distance_mi

    fig = go.Figure()
    fig.add_trace(go.Histogram(x=x0, name='Driving Distance'))
    fig.add_trace(go.Histogram(x=x1, name='Distance as the Crow Flies'))

    # Overlay both histograms
    fig.update_layout(barmode='overlay', title='Distance Histograms', xaxis_title='Distance (miles)')

    # Reduce opacity to see both histograms
    fig.update_traces(opacity=0.75)
    histJSON = json.dumps(fig, cls=PlotlyJSONEncoder)
    return histJSON


def create_plotly_heatmap(tag_df):
    heatmap_df = (
        tag_df.groupby([tag_df.placed_at_datetime.dt.year, tag_df.placed_at_datetime.dt.month])['name'].count().unstack(
            level=0).fillna(0))

    heatmap_df.index = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    fig = px.imshow(heatmap_df.transpose(), labels=dict(x="Month", y="Year", color="Tags"), y=heatmap_df.columns,
                    x=heatmap_df.index, color_continuous_scale='viridis', title='Tags Placed by Month and Year',
                    text_auto=True)

    heatJSON = json.dumps(fig, cls=PlotlyJSONEncoder)
    return heatJSON


def create_bokeh_network(person_df, tag_df):
    G = nx.MultiDiGraph()
    for index, row in tag_df.iterrows():
        G.add_edge(row.placed_by_id, row.found_by_id)

    degrees = dict(nx.degree(G))
    nx.set_node_attributes(G, name='degree', values=degrees)

    edgeweights = {}
    for t in G.edges:
        edgeweights[(t[0], t[1])] = edgeweights.get((t[0], t[1]), 0) + 1

    for t in G.edges:
        G.edges[t[0], t[1], t[2]]['weight'] = edgeweights[(t[0], t[1])] * 3

    # Pick a color palette — Blues8, Reds8, Purples8, Oranges8, Viridis8
    color_palette = Spectral8

    for node in G.nodes:
        G.nodes[node]['x'] = person_df.loc[person_df.person_id == node].convex_hull_center.x.values[0] / 10000
        G.nodes[node]['y'] = person_df.loc[person_df.person_id == node].convex_hull_center.y.values[0] / 10000
        G.nodes[node]['name'] = person_df.loc[person_df.person_id == node].index[0]
        G.nodes[node]['cluster'] = person_df.loc[person_df.person_id == node].cluster.values[0]
        G.nodes[node]['cluster_color'] = color_palette[person_df.loc[person_df.person_id == node].cluster.values[0]]

    number_to_adjust_by = 5
    adjusted_node_size = dict([(node, degree + number_to_adjust_by) for node, degree in nx.degree(G)])
    nx.set_node_attributes(G, name='adjusted_node_size', values=adjusted_node_size)

    # Choose attributes from G network to size and color by — setting manual size (e.g. 10) or color (e.g. 'skyblue') also allowed
    size_by_this_attribute = 'adjusted_node_size'
    color_by_this_attribute = 'cluster_color'

    # Choose a title!
    title = 'Bike Tag Network Graph'

    # Establish which categories will appear when hovering over each node
    HOVER_TOOLTIPS = [("Person", "@name"), ("Cluster", "@cluster"), ("Degree", "@degree")]

    # Create a plot — set dimensions, toolbar, and title
    plot = figure(tooltips=HOVER_TOOLTIPS, tools="pan,wheel_zoom,save,reset", active_scroll='wheel_zoom',
                  x_range=Range1d(-10.1, 10.1), y_range=Range1d(-10.1, 10.1), title=title)

    # Create a network graph object with spring layout
    # https://networkx.github.io/documentation/networkx-1.9/reference/generated/networkx.drawing.layout.spring_layout.html
    network_graph = from_networkx(G, nx.spring_layout, scale=10, center=(0, 0))

    # Set node sizes and colors according to node degree (color as spectrum of color palette)
    minimum_value_color = min(network_graph.node_renderer.data_source.data[color_by_this_attribute])
    maximum_value_color = max(network_graph.node_renderer.data_source.data[color_by_this_attribute])

    # Set node sizes and colors
    network_graph.node_renderer.glyph = Circle(size=size_by_this_attribute, fill_color=color_by_this_attribute)

    # Set edge opacity and width
    network_graph.edge_renderer.glyph = MultiLine(line_alpha=0.5, line_width='weight')

    plot.renderers.append(network_graph)

    return components(plot)
