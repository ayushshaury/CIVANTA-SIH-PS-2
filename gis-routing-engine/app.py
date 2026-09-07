# =========================================================
# NER LOGISTICS ACCESSIBILITY
# GIS + RISK-AWARE ROUTING SYSTEM
# =========================================================

import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import osmnx as osm
import folium

from streamlit_folium import st_folium


# =========================================================
# 1. PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="NER Logistics Routing",
    page_icon="🛣️",
    layout="wide"
)


# =========================================================
# 2. TITLE
# =========================================================

st.title("🛣️ NER Logistics Accessibility & Risk-Aware Routing")

st.markdown(
    """
    **GIS + AI-assisted road risk routing prototype**

    This system compares:
    
    - 🚗 Standard shortest route
    - 🛡️ Risk-aware route
    
    using OpenStreetMap road data and the provided
    road risk prediction database.
    """
)


# =========================================================
# 3. LOAD ROAD RISK DATA
# =========================================================

@st.cache_data
def load_risk_data():

    csv_path = "road_risk_scores.csv"

    df = pd.read_csv(csv_path)

    # Make sure expected columns exist
    required_columns = [
        "road_id",
        "risk_score",
        "predicted_disruption"
    ]

    for column in required_columns:

        if column not in df.columns:

            raise ValueError(
                f"Missing required column: {column}"
            )

    # Convert values to numeric
    df["risk_score"] = pd.to_numeric(
        df["risk_score"],
        errors="coerce"
    )

    df["predicted_disruption"] = pd.to_numeric(
        df["predicted_disruption"],
        errors="coerce"
    )

    # Remove invalid rows
    df = df.dropna(
        subset=[
            "road_id",
            "risk_score"
        ]
    )

    return df


# =========================================================
# 4. LOAD DATA
# =========================================================

try:

    risk_df = load_risk_data()

except Exception as e:

    st.error(
        f"Could not load risk database: {e}"
    )

    st.stop()


# =========================================================
# 5. SIDEBAR
# =========================================================

st.sidebar.header("📍 Route Settings")


# ---------------------------------------------------------
# Default Guwahati coordinates
# ---------------------------------------------------------

DEFAULT_START_LAT = 26.1445
DEFAULT_START_LON = 91.7362

DEFAULT_END_LAT = 26.1158
DEFAULT_END_LON = 91.7086


# ---------------------------------------------------------
# Start location
# ---------------------------------------------------------

st.sidebar.subheader("Start Location")

start_lat = st.sidebar.number_input(
    "Start Latitude",
    value=DEFAULT_START_LAT,
    format="%.6f"
)

start_lon = st.sidebar.number_input(
    "Start Longitude",
    value=DEFAULT_START_LON,
    format="%.6f"
)


# ---------------------------------------------------------
# Destination
# ---------------------------------------------------------

st.sidebar.subheader("Destination")

end_lat = st.sidebar.number_input(
    "Destination Latitude",
    value=DEFAULT_END_LAT,
    format="%.6f"
)

end_lon = st.sidebar.number_input(
    "Destination Longitude",
    value=DEFAULT_END_LON,
    format="%.6f"
)


# ---------------------------------------------------------
# Search radius
# ---------------------------------------------------------

st.sidebar.subheader("OSM Road Network")

dist = st.sidebar.slider(
    "Road network radius (meters)",
    min_value=1000,
    max_value=15000,
    value=5000,
    step=500
)


# ---------------------------------------------------------
# Risk weight
# ---------------------------------------------------------

st.sidebar.subheader("Risk Model")

alpha = st.sidebar.slider(
    "Risk weight",
    min_value=0.0,
    max_value=0.20,
    value=0.05,
    step=0.01
)


beta = st.sidebar.slider(
    "Disruption penalty",
    min_value=0.0,
    max_value=30.0,
    value=15.0,
    step=1.0
)


# =========================================================
# 6. RUN ROUTING
# =========================================================

run_route = st.sidebar.button(
    "🚀 Calculate Routes",
    type="primary"
)


# =========================================================
# 7. ROUTING FUNCTION
# =========================================================

def calculate_routes(
    start_lat,
    start_lon,
    end_lat,
    end_lon,
    dist,
    alpha,
    beta,
    risk_df
):

    # -----------------------------------------------------
    # Download OpenStreetMap road network
    # -----------------------------------------------------

    G = osm.graph_from_point(
        (
            start_lat,
            start_lon
        ),
        dist=dist,
        network_type="drive"
    )

    # -----------------------------------------------------
    # Project graph
    # -----------------------------------------------------

    G = osm.project_graph(G)

    # -----------------------------------------------------
    # Convert input coordinates into projected coordinates
    # -----------------------------------------------------

    start_gdf = osm.projection.project_gdf(
        osm.geocode_to_gdf(
            f"{start_lat}, {start_lon}"
        )
    )

    # -----------------------------------------------------
    # Instead of using projected coordinates from geocoding,
    # convert the original coordinates using graph CRS.
    # -----------------------------------------------------

    import geopandas as gpd

    start_point = gpd.GeoSeries(
        [
            gpd.points_from_xy(
                [start_lon],
                [start_lat]
            )[0]
        ],
        crs="EPSG:4326"
    )

    end_point = gpd.GeoSeries(
        [
            gpd.points_from_xy(
                [end_lon],
                [end_lat]
            )[0]
        ],
        crs="EPSG:4326"
    )

    start_point = start_point.to_crs(
        G.graph["crs"]
    )

    end_point = end_point.to_crs(
        G.graph["crs"]
    )

    # -----------------------------------------------------
    # Find nearest graph nodes
    # -----------------------------------------------------

    orig_node = osm.distance.nearest_nodes(
        G,
        X=start_point.geometry.x.iloc[0],
        Y=start_point.geometry.y.iloc[0]
    )

    dest_node = osm.distance.nearest_nodes(
        G,
        X=end_point.geometry.x.iloc[0],
        Y=end_point.geometry.y.iloc[0]
    )

    # -----------------------------------------------------
    # Create risk lookup
    # -----------------------------------------------------

    risk_lookup = {}

    for _, row in risk_df.iterrows():

        road_id = str(
            row["road_id"]
        )

        risk_lookup[road_id] = {
            "risk_score": float(
                row["risk_score"]
            ),
            "predicted_disruption": int(
                row["predicted_disruption"]
            )
        }

    # -----------------------------------------------------
    # Add risk attributes to every road edge
    # -----------------------------------------------------

    for u, v, key, data in G.edges(
        keys=True,
        data=True
    ):

        # OSM way ID
        osmid = data.get(
            "osmid",
            None
        )

        # OSMnx may store osmid as a list
        if isinstance(
            osmid,
            list
        ):

            osmid_list = osmid

        else:

            osmid_list = [osmid]

        risk_score = 0.0
        predicted_disruption = 0

        # -------------------------------------------------
        # Try matching OSM way ID to CSV
        # -------------------------------------------------

        for osm_id in osmid_list:

            if osm_id is None:
                continue

            road_id = f"way/{osm_id}"

            if road_id in risk_lookup:

                risk_score = risk_lookup[
                    road_id
                ]["risk_score"]

                predicted_disruption = risk_lookup[
                    road_id
                ]["predicted_disruption"]

                break

        # -------------------------------------------------
        # Store attributes
        # -------------------------------------------------

        data["risk_score_val"] = risk_score

        data["is_disrupted"] = predicted_disruption

        # -------------------------------------------------
        # Distance
        # -------------------------------------------------

        length = data.get(
            "length",
            1
        )

        # -------------------------------------------------
        # Risk penalty
        #
        # Higher risk = higher routing cost
        # -------------------------------------------------

        risk_penalty = (
            1
            + (
                alpha
                * risk_score
            )
            + (
                beta
                * predicted_disruption
            )
        )

        data["risk_cost"] = (
            length
            * risk_penalty
        )

    # -----------------------------------------------------
    # STANDARD SHORTEST ROUTE
    # -----------------------------------------------------

    try:

        std_route = nx.shortest_path(
            G,
            orig_node,
            dest_node,
            weight="length"
        )

    except nx.NetworkXNoPath:

        raise ValueError(
            "No standard route found."
        )

    # -----------------------------------------------------
    # RISK-AWARE ROUTE
    # -----------------------------------------------------

    try:

        risk_route = nx.shortest_path(
            G,
            orig_node,
            dest_node,
            weight="risk_cost"
        )

    except nx.NetworkXNoPath:

        raise ValueError(
            "No risk-aware route found."
        )

    # -----------------------------------------------------
    # ROUTE STATISTICS
    # -----------------------------------------------------

    def get_route_stats(
        graph,
        route
    ):

        total_distance = 0.0

        total_risk = 0.0

        disrupted_edges = 0

        edge_count = 0

        for u, v in zip(
            route[:-1],
            route[1:]
        ):

            edge_data = graph.get_edge_data(
                u,
                v
            )

            if not edge_data:
                continue

            # -------------------------------------------------
            # Select the edge with the smallest risk cost
            # -------------------------------------------------

            edge = min(
                edge_data.values(),
                key=lambda x: x.get(
                    "risk_cost",
                    x.get(
                        "length",
                        float("inf")
                    )
                )
            )

            total_distance += edge.get(
                "length",
                0
            )

            total_risk += edge.get(
                "risk_score_val",
                0
            )

            disrupted_edges += edge.get(
                "is_disrupted",
                0
            )

            edge_count += 1

        # -----------------------------------------------------
        # Average risk
        # -----------------------------------------------------

        if edge_count > 0:

            average_risk = (
                total_risk
                / edge_count
            )

        else:

            average_risk = 0

        return {

            "distance_km":
                total_distance / 1000,

            "average_risk":
                average_risk,

            "disrupted_edges":
                disrupted_edges,

            "edge_count":
                edge_count
        }

    # -----------------------------------------------------
    # Calculate statistics
    # -----------------------------------------------------

    std_stats = get_route_stats(
        G,
        std_route
    )

    risk_stats = get_route_stats(
        G,
        risk_route
    )

    return (
        G,
        std_route,
        risk_route,
        std_stats,
        risk_stats
    )


# =========================================================
# 8. RUN CALCULATION
# =========================================================

if run_route:

    with st.spinner(
        "Downloading road network and calculating routes..."
    ):

        try:

            (
                G,
                std_route,
                risk_route,
                std_stats,
                risk_stats
            ) = calculate_routes(
                start_lat,
                start_lon,
                end_lat,
                end_lon,
                dist,
                alpha,
                beta,
                risk_df
            )

            st.session_state[
                "G"
            ] = G

            st.session_state[
                "std_route"
            ] = std_route

            st.session_state[
                "risk_route"
            ] = risk_route

            st.session_state[
                "std_stats"
            ] = std_stats

            st.session_state[
                "risk_stats"
            ] = risk_stats

            st.success(
                "Routes calculated successfully!"
            )

        except Exception as e:

            st.error(
                f"Routing failed: {e}"
            )

            st.stop()


# =========================================================
# 9. DISPLAY RESULTS
# =========================================================

if (
    "std_route"
    in st.session_state
):

    G = st.session_state[
        "G"
    ]

    std_route = st.session_state[
        "std_route"
    ]

    risk_route = st.session_state[
        "risk_route"
    ]

    std_stats = st.session_state[
        "std_stats"
    ]

    risk_stats = st.session_state[
        "risk_stats"
    ]


    # =====================================================
    # 9A. STANDARD ROUTE
    # =====================================================

    st.subheader(
        "🚗 Standard Shortest Route"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Distance",
            f"{std_stats['distance_km']:.2f} km"
        )

    with col2:

        st.metric(
            "Average Risk",
            f"{std_stats['average_risk']:.2f}"
        )

    with col3:

        st.metric(
            "Disrupted Roads",
            std_stats["disrupted_edges"]
        )


    # =====================================================
    # 9B. RISK-AWARE ROUTE
    # =====================================================

    st.subheader(
        "🛡️ Risk-Aware Route"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Distance",
            f"{risk_stats['distance_km']:.2f} km"
        )

    with col2:

        st.metric(
            "Average Risk",
            f"{risk_stats['average_risk']:.2f}"
        )

    with col3:

        st.metric(
            "Disrupted Roads",
            risk_stats["disrupted_edges"]
        )


    # =====================================================
    # 9C. COMPARISON
    # =====================================================

    st.subheader(
        "📊 Route Comparison"
    )

    distance_difference = (
        risk_stats["distance_km"]
        - std_stats["distance_km"]
    )

    risk_difference = (
        risk_stats["average_risk"]
        - std_stats["average_risk"]
    )

    disruption_difference = (
        risk_stats["disrupted_edges"]
        - std_stats["disrupted_edges"]
    )

    comparison_df = pd.DataFrame(
        {
            "Metric": [
                "Distance (km)",
                "Average Risk",
                "Disrupted Roads"
            ],

            "Standard Route": [
                std_stats[
                    "distance_km"
                ],

                std_stats[
                    "average_risk"
                ],

                std_stats[
                    "disrupted_edges"
                ]
            ],

            "Risk-Aware Route": [
                risk_stats[
                    "distance_km"
                ],

                risk_stats[
                    "average_risk"
                ],

                risk_stats[
                    "disrupted_edges"
                ]
            ]
        }
    )

    st.dataframe(
        comparison_df,
        use_container_width=True
    )


    # =====================================================
    # 9D. ROUTING INSIGHT
    # =====================================================

    st.subheader(
        "🧠 Routing Insight"
    )

    if (
        risk_stats["average_risk"]
        < std_stats["average_risk"]
    ):

        st.success(
            f"""
            The risk-aware route reduces average road risk
            by approximately
            {abs(risk_difference):.2f}
            risk points.
            
            Additional distance:
            {max(distance_difference, 0):.2f} km.
            """
        )

    elif (
        risk_stats["average_risk"]
        > std_stats["average_risk"]
    ):

        st.warning(
            """
            The current risk weighting did not produce
            a lower-risk route for this origin and destination.
            
            Try increasing the Risk Weight or Disruption
            Penalty from the sidebar.
            """
        )

    else:

        st.info(
            "Both routes have approximately the same average risk."
        )


    # =====================================================
    # 10. MAP
    # =====================================================

    st.subheader(
        "🗺️ GIS Route Map"
    )

    # -----------------------------------------------------
    # Convert graph back to latitude/longitude
    # -----------------------------------------------------

    G_map = osm.project_graph(
        G,
        to_crs="EPSG:4326"
    )

    # -----------------------------------------------------
    # Route coordinates
    # -----------------------------------------------------

    def route_to_coordinates(
        graph,
        route
    ):

        coordinates = []

        for node in route:

            x = graph.nodes[
                node
            ]["x"]

            y = graph.nodes[
                node
            ]["y"]

            coordinates.append(
                [y, x]
            )

        return coordinates


    std_coordinates = route_to_coordinates(
        G_map,
        std_route
    )

    risk_coordinates = route_to_coordinates(
        G_map,
        risk_route
    )


    # -----------------------------------------------------
    # Map center
    # -----------------------------------------------------

    map_center = [
        (
            start_lat
            + end_lat
        ) / 2,

        (
            start_lon
            + end_lon
        ) / 2
    ]


    route_map = folium.Map(
        location=map_center,
        zoom_start=13,
        tiles="OpenStreetMap"
    )


    # =====================================================
    # STANDARD ROUTE
    # =====================================================

    folium.PolyLine(
        std_coordinates,
        weight=6,
        opacity=0.7,
        tooltip=(
            "🚗 Standard Shortest Route"
        )
    ).add_to(
        route_map
    )


    # =====================================================
    # RISK-AWARE ROUTE
    # =====================================================

    folium.PolyLine(
        risk_coordinates,
        weight=6,
        opacity=0.9,
        tooltip=(
            "🛡️ Risk-Aware Route"
        )
    ).add_to(
        route_map
    )


    # =====================================================
    # START MARKER
    # =====================================================

    folium.Marker(
        location=[
            start_lat,
            start_lon
        ],
        popup="START",
        tooltip="Start Location",
        icon=folium.Icon(
            icon="play",
            prefix="fa"
        )
    ).add_to(
        route_map
    )


    # =====================================================
    # DESTINATION MARKER
    # =====================================================

    folium.Marker(
        location=[
            end_lat,
            end_lon
        ],
        popup="DESTINATION",
        tooltip="Destination",
        icon=folium.Icon(
            icon="flag",
            prefix="fa"
        )
    ).add_to(
        route_map
    )


    # =====================================================
    # DISPLAY MAP
    # =====================================================

    st_folium(
        route_map,
        width=None,
        height=650
    )


# =========================================================
# 11. DATABASE INFORMATION
# =========================================================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "📊 Risk Database"
)

st.sidebar.write(
    f"Road records: **{len(risk_df)}**"
)

st.sidebar.write(
    f"Average risk: **{risk_df['risk_score'].mean():.2f}**"
)

st.sidebar.write(
    f"Maximum risk: **{risk_df['risk_score'].max():.2f}**"
)

st.sidebar.write(
    "Predicted disruptions: "
    f"**{int(risk_df['predicted_disruption'].sum())}**"
)


# =========================================================
# 12. FOOTER
# =========================================================

st.markdown("---")

st.caption(
    "NER Logistics Accessibility Intelligence Platform "
    "| GIS + Risk-Aware Routing Prototype"
)
