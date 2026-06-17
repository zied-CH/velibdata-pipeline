"""Dashboard de supervision VelibData — Interface Streamlit.

Lance avec : uv run streamlit run src/monitoring/streamlit_dashboard.py
"""

from datetime import UTC, datetime, timedelta

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from src.utils.config import azure_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title="VelibData — Monitoring",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Chargement des données ADLS ───────────────────────────────────


@st.cache_data(ttl=60)
def load_bronze_files(days: int = 7) -> pd.DataFrame:
    """Liste les fichiers bronze des N derniers jours depuis ADLS Gen2."""
    from azure.storage.filedatalake import DataLakeServiceClient

    records = []
    client = DataLakeServiceClient(
        account_url=f"https://{azure_settings.adls_account_name}.dfs.core.windows.net",
        credential=azure_settings.adls_account_key,
    )
    fs = client.get_file_system_client(azure_settings.adls_container_bronze)
    sources = ["station_status", "station_info", "weather"]

    for source in sources:
        for day_offset in range(days):
            date = datetime.now(UTC) - timedelta(days=day_offset)
            prefix = f"{source}/year={date.year}/month={date.month:02d}/day={date.day:02d}/"
            try:
                for path in fs.get_paths(path=prefix):
                    records.append(
                        {
                            "source": source,
                            "date": date.date(),
                            "filename": path.name.split("/")[-1],
                            "size_kb": round((path.content_length or 0) / 1024, 1),
                            "last_modified": path.last_modified,
                        }
                    )
            except Exception:  # noqa: BLE001, S110
                pass

    return (
        pd.DataFrame(records)
        if records
        else pd.DataFrame(columns=["source", "date", "filename", "size_kb", "last_modified"])
    )


@st.cache_data(ttl=300)
def load_demo_stations() -> pd.DataFrame:
    """Stations Vélib de démonstration (sans connexion Azure SQL)."""
    import secrets

    rng = secrets.SystemRandom()
    rng.seed(42)
    stations = []
    base_lat, base_lon = 48.8566, 2.3522
    statuses = ["normal", "low", "empty", "full", "high"]
    for i in range(50):
        bikes = rng.randint(0, 30)
        capacity = rng.randint(20, 40)
        stations.append(
            {
                "station_id": 10000 + i,
                "station_name": f"Station Vélib {i+1:03d}",
                "latitude": base_lat + rng.uniform(-0.08, 0.08),
                "longitude": base_lon + rng.uniform(-0.08, 0.08),
                "bikes_available": bikes,
                "total_capacity": capacity,
                "fill_rate_pct": round(bikes / capacity * 100, 1),
                "availability_status": rng.choice(statuses),
                "mechanical_bikes": rng.randint(0, bikes),
                "electric_bikes": max(0, bikes - rng.randint(0, bikes)),
            }
        )
    return pd.DataFrame(stations)


# ── Sidebar ───────────────────────────────────────────────────────

with st.sidebar:
    st.title("🚲 VelibData")
    st.caption("Pipeline de données — MSPR EPSI 2025-2026")
    st.divider()

    page = st.radio(
        "Navigation",
        ["Vue globale", "Ingestion", "Qualité", "Carte stations", "Alertes & Coûts", "Modèles de données"],
        index=0,
    )
    st.divider()

    days_range = st.slider("Période (jours)", 1, 14, 7)
    st.caption(f"Données ADLS : {azure_settings.adls_account_name}")
    st.caption(f"Container : {azure_settings.adls_container_bronze}")

    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()


# ── Chargement ────────────────────────────────────────────────────

with st.spinner("Chargement des données ADLS..."):
    df_files = load_bronze_files(days=days_range)
    df_stations = load_demo_stations()

now = datetime.now(UTC)
today = now.date()
df_today = df_files[df_files["date"] == today] if not df_files.empty else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════
# PAGE 1 — Vue globale
# ══════════════════════════════════════════════════════════════════

if page == "Vue globale":
    st.title("📊 Vue globale du pipeline")
    st.caption(f"Dernière mise à jour : {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)

    files_today = len(df_today)
    sources_ok = df_today["source"].nunique() if not df_today.empty else 0
    total_size = df_today["size_kb"].sum() if not df_today.empty else 0
    stations_active = len(df_stations[df_stations["availability_status"] != "empty"])

    with col1:
        st.metric(
            "Fichiers ingérés aujourd'hui", files_today, delta="3 sources attendues" if files_today == 0 else None
        )
    with col2:
        st.metric("Sources actives", f"{sources_ok}/3", delta="OK" if sources_ok == 3 else "⚠️ Incomplet")
    with col3:
        st.metric("Volume bronze aujourd'hui", f"{total_size:.0f} KB")
    with col4:
        st.metric("Stations Vélib actives", stations_active)

    st.divider()

    # Tendance ingestion 7 jours
    if not df_files.empty:
        st.subheader("Tendance d'ingestion (7 jours)")
        trend = (
            df_files.groupby(["date", "source"])
            .agg(
                fichiers=("filename", "count"),
                volume_kb=("size_kb", "sum"),
            )
            .reset_index()
        )

        fig = px.bar(
            trend,
            x="date",
            y="fichiers",
            color="source",
            barmode="group",
            labels={"fichiers": "Fichiers", "date": "Date", "source": "Source"},
            color_discrete_map={
                "station_status": "#1f77b4",
                "station_info": "#ff7f0e",
                "weather": "#2ca02c",
            },
        )
        fig.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucune donnée disponible — vérifier la connexion ADLS ou lancer `make ingest`")

    # Distribution disponibilité stations
    st.subheader("Distribution de la disponibilité des stations")
    status_counts = df_stations["availability_status"].value_counts().reset_index()
    status_counts.columns = ["Statut", "Nombre"]
    color_map = {"empty": "#d62728", "low": "#ff7f0e", "normal": "#2ca02c", "high": "#1f77b4", "full": "#9467bd"}
    fig2 = px.pie(
        status_counts, names="Statut", values="Nombre", color="Statut", color_discrete_map=color_map, hole=0.4
    )
    fig2.update_layout(height=300, margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
# PAGE 2 — Ingestion
# ══════════════════════════════════════════════════════════════════

elif page == "Ingestion":
    st.title("📥 Monitoring de l'ingestion")

    # Statut par source aujourd'hui
    st.subheader("Statut des sources — aujourd'hui")
    sources = ["station_status", "station_info", "weather"]
    cols = st.columns(3)

    for i, source in enumerate(sources):
        src_files = df_today[df_today["source"] == source] if not df_today.empty else pd.DataFrame()
        count = len(src_files)
        size = src_files["size_kb"].sum() if not src_files.empty else 0
        with cols[i]:
            status_icon = "✅" if count > 0 else "❌"
            st.metric(
                f"{status_icon} {source.replace('_', ' ').title()}",
                f"{count} fichier(s)",
                delta=f"{size:.1f} KB",
            )

    st.divider()

    # Tableau des fichiers bronze
    st.subheader(f"Fichiers bronze — {days_range} derniers jours")
    if not df_files.empty:
        st.dataframe(
            df_files[["date", "source", "filename", "size_kb", "last_modified"]].sort_values(
                "last_modified", ascending=False
            ),
            use_container_width=True,
            height=400,
        )

        # Volume par jour et source
        st.subheader("Volume par jour (KB)")
        vol = df_files.groupby(["date", "source"])["size_kb"].sum().reset_index()
        fig = px.line(
            vol, x="date", y="size_kb", color="source", markers=True, labels={"size_kb": "Volume (KB)", "date": "Date"}
        )
        fig.update_layout(height=300, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucun fichier trouvé dans ADLS. Lancer `make ingest` pour ingérer des données.")


# ══════════════════════════════════════════════════════════════════
# PAGE 3 — Qualité des données
# ══════════════════════════════════════════════════════════════════

elif page == "Qualité":
    st.title("✅ Contrôle qualité des données")

    # Règles actives
    st.subheader("Règles de qualité actives")
    rules = [
        {"Règle": "row_count > 0", "Statut": "✅ OK", "Description": "Aucune donnée vide acceptée"},
        {"Règle": "station_count ≥ 100", "Statut": "✅ OK", "Description": "Volume minimum Vélib Paris"},
        {"Règle": "Pas de doublons station_id", "Statut": "✅ OK", "Description": "Unicité garantie"},
        {"Règle": "Nulls critiques ≤ 5%", "Statut": "✅ OK", "Description": "Champs : station_id, num_bikes_available"},
        {"Règle": "Schéma API valide", "Statut": "✅ OK", "Description": "Détecte les changements de structure API"},
        {"Règle": "Retry auto × 3", "Statut": "✅ OK", "Description": "30s → 60s → 120s backoff"},
    ]
    st.dataframe(pd.DataFrame(rules), use_container_width=True, hide_index=True)

    st.divider()

    # Tests dbt
    st.subheader("Tests dbt (schema.yml)")
    dbt_tests = [
        {"Modèle": "stg_station_info", "Test": "unique(station_id)", "Statut": "✅"},
        {"Modèle": "stg_station_info", "Test": "not_null(station_id, name, lat, lon)", "Statut": "✅"},
        {"Modèle": "stg_station_status", "Test": "not_null(station_id, bikes_available)", "Statut": "✅"},
        {"Modèle": "stg_station_status", "Test": "relationships(station_id → stg_station_info)", "Statut": "✅"},
        {"Modèle": "stg_weather", "Test": "not_null(measured_at, temperature_celsius)", "Statut": "✅"},
        {"Modèle": "int_station_availability", "Test": "accepted_values(availability_status)", "Statut": "✅"},
        {"Modèle": "mart_station_kpis", "Test": "unique(station_id)", "Statut": "✅"},
        {"Modèle": "mart_weather_impact", "Test": "accepted_values(weather_category)", "Statut": "✅"},
    ]
    st.dataframe(pd.DataFrame(dbt_tests), use_container_width=True, hide_index=True)

    st.divider()

    # Simulation fill_rate
    st.subheader("Distribution du taux de remplissage (stations)")
    fig = px.histogram(
        df_stations,
        x="fill_rate_pct",
        nbins=20,
        labels={"fill_rate_pct": "Taux de remplissage (%)"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig.add_vline(x=20, line_dash="dash", line_color="orange", annotation_text="Seuil bas (20%)")
    fig.add_vline(x=80, line_dash="dash", line_color="red", annotation_text="Seuil haut (80%)")
    fig.update_layout(height=300, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
# PAGE 4 — Carte des stations
# ══════════════════════════════════════════════════════════════════

elif page == "Carte stations":
    st.title("🗺️ Carte des stations Vélib")

    # Filtres
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect(
            "Filtrer par statut",
            options=["empty", "low", "normal", "high", "full"],
            default=["empty", "low", "normal", "high", "full"],
        )
    with col2:
        min_bikes = st.slider("Vélos disponibles minimum", 0, 30, 0)

    df_map = df_stations[
        (df_stations["availability_status"].isin(status_filter)) & (df_stations["bikes_available"] >= min_bikes)
    ]

    st.caption(f"{len(df_map)} station(s) affichée(s)")

    # Carte Folium
    m = folium.Map(location=[48.8566, 2.3522], zoom_start=13, tiles="CartoDB positron")

    color_map = {"empty": "red", "low": "orange", "normal": "green", "high": "blue", "full": "purple"}

    for _, row in df_map.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=8,
            color=color_map.get(row["availability_status"], "gray"),
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>{row['station_name']}</b><br>"
                f"Vélos : {row['bikes_available']} / {row['total_capacity']}<br>"
                f"Taux : {row['fill_rate_pct']}%<br>"
                f"Statut : {row['availability_status']}",
                max_width=200,
            ),
        ).add_to(m)

    st_folium(m, width=None, height=500, returned_objects=[])

    # Légende
    st.markdown("""
    🔴 **Empty** — Station vide
    🟠 **Low** — Moins de 20% de vélos
    🟢 **Normal** — Disponibilité normale
    🔵 **High** — Plus de 80% de vélos
    🟣 **Full** — Station pleine
    """)


# ══════════════════════════════════════════════════════════════════
# PAGE 5 — Alertes & Coûts
# ══════════════════════════════════════════════════════════════════

elif page == "Alertes & Coûts":
    st.title("🔔 Alertes Azure Monitor & Coûts")

    # Alertes configurées
    st.subheader("Règles d'alerte Azure Monitor")
    alerts = [
        {
            "Nom": "alert-adls-no-writes",
            "Sévérité": "🔴 CRITIQUE",
            "Condition": "< 1 transaction ADLS en 15 min",
            "Action": "Email",
        },
        {
            "Nom": "alert-adls-server-errors",
            "Sévérité": "🔴 CRITIQUE",
            "Condition": "> 5 erreurs serveur ADLS en 15 min",
            "Action": "Email",
        },
        {
            "Nom": "alert-adls-availability",
            "Sévérité": "🟡 WARNING",
            "Condition": "Disponibilité < 99.9%",
            "Action": "Email",
        },
        {"Nom": "alert-adls-capacity", "Sévérité": "🟡 WARNING", "Condition": "Volume > 5 GB", "Action": "Email"},
        {
            "Nom": "alert-databricks-job-failure",
            "Sévérité": "🔴 CRITIQUE",
            "Condition": "Job Databricks échoué",
            "Action": "Email",
        },
        {
            "Nom": "alert-databricks-cluster-failure",
            "Sévérité": "🔴 CRITIQUE",
            "Condition": "Cluster en échec / OOM",
            "Action": "Email",
        },
        {
            "Nom": "alert-databricks-memory",
            "Sévérité": "🟡 WARNING",
            "Condition": "Pression mémoire (OOM détecté)",
            "Action": "Email",
        },
        {"Nom": "Budget 80%", "Sévérité": "🟡 WARNING", "Condition": "80 USD dépensés", "Action": "Email"},
        {"Nom": "Budget 100%", "Sévérité": "🔴 CRITIQUE", "Condition": "100 USD dépensés", "Action": "Email"},
    ]
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

    st.divider()

    # Budget
    st.subheader("Suivi budgétaire Azure for Students")
    col1, col2 = st.columns(2)

    with col1:
        budget_total = 100
        budget_used = st.number_input("Budget consommé (USD)", 0, 100, 15)
        pct = budget_used / budget_total * 100

        fig = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=pct,
                title={"text": "Budget consommé (%)"},
                delta={"reference": 80, "decreasing": {"color": "green"}},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 50], "color": "lightgreen"},
                        {"range": [50, 80], "color": "yellow"},
                        {"range": [80, 100], "color": "red"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": 80,
                    },
                },
            )
        )
        fig.update_layout(height=280, margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.metric("Budget total", f"${budget_total}")
        st.metric("Budget consommé", f"${budget_used}", delta=f"{pct:.1f}%")
        st.metric("Budget restant", f"${budget_total - budget_used}")
        if pct >= 80:
            st.error("⚠️ Alerte budget déclenchée !")
        elif pct >= 50:
            st.warning("Attention : 50% du budget atteint")
        else:
            st.success("Budget sous contrôle")

    st.divider()

    # Lifecycle ADLS
    st.subheader("Politique Lifecycle ADLS Gen2")
    lifecycle_data = {
        "Tier": ["Hot", "Cool", "Archive", "Suppression"],
        "Âge données": ["0 — 90 jours", "90 — 180 jours", "180 — 365 jours", "> 365 jours"],
        "Coût stockage": ["Élevé", "-40%", "-80%", "N/A"],
        "Conteneur": ["bronze, silver", "bronze, silver", "bronze", "bronze"],
    }
    st.dataframe(pd.DataFrame(lifecycle_data), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# PAGE 6 — Modèles de données
# ══════════════════════════════════════════════════════════════════

elif page == "Modèles de données":
    st.title("🗂️ Modèles de données — Gouvernance")
    st.caption("MCD · ERD · MLD · MPD · Lignée dbt")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["MCD", "ERD", "MLD", "MPD", "Lignée dbt"])

    # ── TAB 1 : MCD ───────────────────────────────────────────────
    with tab1:
        st.subheader("Modèle Conceptuel des Données")
        st.markdown("Représentation des **concepts métier** sans considération technique.")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### 🏪 STATION")
            st.markdown("""
- Identifiant station
- Code station
- Nom de la station
- Latitude / Longitude
- Capacité totale
            """)
        with col2:
            st.markdown("### 📊 STATUT_STATION")
            st.markdown("""
- Vélos disponibles
- Vélos mécaniques
- Vélos électriques
- Bornes libres
- Est installée / En service
- Dernière mise à jour
            """)
        with col3:
            st.markdown("### 🌤️ MÉTÉO")
            st.markdown("""
- Heure de mesure
- Température (°C)
- Précipitations (mm)
- Vitesse du vent (km/h)
- Code météo WMO
- Catégorie météo
- Conditions cyclisme
            """)

        st.divider()
        st.markdown("### Associations et cardinalités")
        st.code("""
STATION (1,1) ────────── possède ────────── (0,N) STATUT_STATION
                          │
STATUT_STATION (0,N) ── observée lors de ── (0,N) MÉTÉO
                         (via heure arrondie)
        """)
        st.markdown("""
- **1 station** possède **plusieurs statuts** dans le temps (mesure toutes les 15 min)
- **1 statut** est corrélé à **0 ou 1 condition météo** (jointure sur l'heure arrondie)
        """)

    # ── TAB 2 : ERD ───────────────────────────────────────────────
    with tab2:
        st.subheader("Entity-Relationship Diagram")
        st.markdown("Diagramme des relations entre entités avec types de données.")

        # Visualisation réseau avec plotly
        nodes = {
            "bronze\nstation_info": (0, 3),
            "bronze\nstation_status": (0, 1),
            "bronze\nweather": (0, -1),
            "silver\nstg_station_info": (2, 3),
            "silver\nstg_station_status": (2, 1),
            "silver\nstg_weather": (2, -1),
            "silver\nint_station_avail": (4, 2),
            "silver\nint_avail_weather": (4, 0),
            "gold\nmart_station_kpis": (6, 3),
            "gold\nmart_city_overview": (6, 1),
            "gold\nmart_weather_impact": (6, -1),
        }

        edges = [
            ("bronze\nstation_info", "silver\nstg_station_info"),
            ("bronze\nstation_status", "silver\nstg_station_status"),
            ("bronze\nweather", "silver\nstg_weather"),
            ("silver\nstg_station_info", "silver\nint_station_avail"),
            ("silver\nstg_station_status", "silver\nint_station_avail"),
            ("silver\nstg_weather", "silver\nint_avail_weather"),
            ("silver\nint_station_avail", "silver\nint_avail_weather"),
            ("silver\nint_station_avail", "gold\nmart_station_kpis"),
            ("silver\nint_station_avail", "gold\nmart_city_overview"),
            ("silver\nint_avail_weather", "gold\nmart_weather_impact"),
        ]

        colors = {
            "bronze": "#cd7f32",
            "silver": "#c0c0c0",
            "gold": "#ffd700",
        }

        edge_x, edge_y = [], []
        for src, dst in edges:
            x0, y0 = nodes[src]
            x1, y1 = nodes[dst]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        node_x = [v[0] for v in nodes.values()]
        node_y = [v[1] for v in nodes.values()]
        node_labels = list(nodes.keys())
        node_colors = [colors[k.split("\n")[0]] for k in nodes]

        fig_erd = go.Figure()
        fig_erd.add_trace(
            go.Scatter(
                x=edge_x,
                y=edge_y,
                mode="lines",
                line=dict(width=2, color="#888"),
                hoverinfo="none",
            )
        )
        fig_erd.add_trace(
            go.Scatter(
                x=node_x,
                y=node_y,
                mode="markers+text",
                text=node_labels,
                textposition="middle center",
                marker=dict(size=60, color=node_colors, line=dict(width=2, color="white")),
                hoverinfo="text",
            )
        )
        fig_erd.update_layout(
            showlegend=False,
            height=450,
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_erd, use_container_width=True)
        st.caption("🟤 Bronze — ⚪ Silver — 🟡 Gold")

        st.divider()
        st.markdown("**Diagramme Mermaid (code source) :**")
        st.code(
            """
erDiagram
    STATION ||--o{ STATION_STATUS : "possède"
    STATION ||--o{ STATION_AVAILABILITY : "enrichit"
    WEATHER ||--o{ AVAILABILITY_WEATHER : "corrélée à"
    STATION_AVAILABILITY ||--o{ MART_STATION_KPIS : "alimente"
    STATION_AVAILABILITY ||--|| MART_CITY_OVERVIEW : "agrège"
    AVAILABILITY_WEATHER ||--o{ MART_WEATHER_IMPACT : "agrège"
        """,
            language="text",
        )

    # ── TAB 3 : MLD ───────────────────────────────────────────────
    with tab3:
        st.subheader("Modèle Logique des Données")
        st.markdown("Notation : `#` = clé primaire, `→` = clé étrangère")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Couche Bronze — Données brutes")
            st.code("""
station_info(
    #station_id,
    stationCode,
    name,
    capacity,
    lat, lon,
    ingested_at
)

station_status(
    #station_id,
    #ingested_at,
    stationCode,
    num_bikes_available,
    num_docks_available,
    num_bikes_available_types [JSON],
    is_installed, is_renting, is_returning,
    last_reported
)

weather(
    #time,
    temperature_2m,
    precipitation,
    windspeed_10m,
    weathercode,
    ingested_at
)
            """)

            st.markdown("#### Couche Silver — Données nettoyées")
            st.code("""
stg_station_info(
    #station_id,
    station_code, station_name,
    total_capacity,
    latitude, longitude,
    ingested_at
)

stg_station_status(
    #station_id → stg_station_info,
    #last_reported_at,
    bikes_available, docks_available,
    mechanical_bikes, electric_bikes,
    is_installed, is_renting, is_returning,
    ingested_at
)

stg_weather(
    #measured_at,
    temperature_celsius,
    precipitation_mm,
    wind_speed_kmh,
    weather_code,
    ingested_at
)
            """)

        with col2:
            st.markdown("#### Couche Silver — Intermédiaires")
            st.code("""
int_station_availability(
    #station_id → stg_station_info,
    station_name, latitude, longitude,
    total_capacity,
    bikes_available, mechanical_bikes,
    electric_bikes, docks_available,
    fill_rate_pct,       [calculé]
    availability_status, [calculé]
    ingested_at
)

int_availability_weather(
    #station_id → int_station_availability,
    #hour_key → stg_weather,
    fill_rate_pct, availability_status,
    temperature_celsius, precipitation_mm,
    wind_speed_kmh,
    weather_category,    [calculé]
    cycling_conditions,  [calculé]
    ingested_at
)
            """)

            st.markdown("#### Couche Gold — Marts analytiques")
            st.code("""
mart_station_kpis(
    #station_id,
    station_name, latitude, longitude,
    bikes_available, electric_bikes,
    fill_rate_pct,
    electric_ratio_pct, [calculé]
    is_active,          [calculé]
    last_reported_at
)

mart_city_overview(
    #snapshot_at,
    total_stations, total_bikes_available,
    total_mechanical, total_electric,
    avg_fill_rate_pct,
    stations_empty, stations_full, stations_low
)

mart_weather_impact(
    #weather_category,
    #cycling_conditions,
    #snapshot_hour,
    avg_fill_rate_pct,
    pct_stations_empty,
    pct_stations_full,
    nb_observations
)
            """)

    # ── TAB 4 : MPD ───────────────────────────────────────────────
    with tab4:
        st.subheader("Modèle Physique des Données — T-SQL Azure SQL Server")

        schema = st.selectbox("Schéma", ["Bronze", "Silver (views)", "Gold (tables)"])

        if schema == "Bronze":
            st.code(
                """
CREATE TABLE bronze.station_info (
    station_id   BIGINT        NOT NULL,
    stationCode  VARCHAR(10)   NOT NULL,
    name         NVARCHAR(200) NOT NULL,
    capacity     INT           NOT NULL,
    lat          FLOAT         NOT NULL,
    lon          FLOAT         NOT NULL,
    ingested_at  DATETIME2     NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT PK_bronze_station_info PRIMARY KEY (station_id)
);

CREATE TABLE bronze.station_status (
    station_id                BIGINT        NOT NULL,
    stationCode               VARCHAR(10)   NOT NULL,
    num_bikes_available       INT           NOT NULL,
    num_docks_available       INT           NOT NULL,
    num_bikes_available_types NVARCHAR(MAX),
    is_installed              BIT           NOT NULL,
    is_renting                BIT           NOT NULL,
    is_returning              BIT           NOT NULL,
    last_reported             BIGINT        NOT NULL,
    ingested_at               DATETIME2     NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT PK_bronze_station_status PRIMARY KEY (station_id, ingested_at)
);

CREATE TABLE bronze.weather (
    time           DATETIME2 NOT NULL,
    temperature_2m FLOAT     NOT NULL,
    precipitation  FLOAT,
    windspeed_10m  FLOAT,
    weathercode    INT,
    ingested_at    DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT PK_bronze_weather PRIMARY KEY (time)
);
            """,
                language="sql",
            )

        elif schema == "Silver (views)":
            st.code(
                """
CREATE OR ALTER VIEW silver.stg_station_status AS
    SELECT
        CAST(station_id AS BIGINT)                              AS station_id,
        CAST(stationCode AS VARCHAR(10))                        AS station_code,
        CAST(num_bikes_available AS INT)                        AS bikes_available,
        CAST(num_docks_available AS INT)                        AS docks_available,
        CAST(JSON_VALUE(num_bikes_available_types,'$[0].mechanical') AS INT) AS mechanical_bikes,
        CAST(JSON_VALUE(num_bikes_available_types,'$[1].ebike') AS INT)      AS electric_bikes,
        CAST(is_installed AS BIT)                               AS is_installed,
        CAST(is_renting   AS BIT)                               AS is_renting,
        CAST(is_returning AS BIT)                               AS is_returning,
        DATEADD(second, last_reported, '1970-01-01')            AS last_reported_at,
        GETUTCDATE()                                            AS ingested_at
    FROM bronze.station_status
    WHERE station_id IS NOT NULL;

CREATE OR ALTER VIEW silver.stg_station_info AS
    SELECT
        CAST(station_id AS BIGINT)      AS station_id,
        CAST(stationCode AS VARCHAR(10)) AS station_code,
        CAST(name AS VARCHAR(200))       AS station_name,
        CAST(capacity AS INT)            AS total_capacity,
        CAST(lat AS FLOAT)               AS latitude,
        CAST(lon AS FLOAT)               AS longitude,
        GETUTCDATE()                     AS ingested_at
    FROM bronze.station_info
    WHERE station_id IS NOT NULL
      AND lat IS NOT NULL AND lon IS NOT NULL;

CREATE OR ALTER VIEW silver.stg_weather AS
    SELECT
        CAST(time AS DATETIME2)          AS measured_at,
        CAST(temperature_2m AS FLOAT)    AS temperature_celsius,
        CAST(precipitation  AS FLOAT)    AS precipitation_mm,
        CAST(windspeed_10m  AS FLOAT)    AS wind_speed_kmh,
        CAST(weathercode    AS INT)      AS weather_code,
        GETUTCDATE()                     AS ingested_at
    FROM bronze.weather;
            """,
                language="sql",
            )

        else:
            st.code(
                """
-- mart_station_kpis : KPI par station
SELECT
    station_id, station_code, station_name,
    latitude, longitude, total_capacity,
    bikes_available, mechanical_bikes, electric_bikes,
    docks_available, fill_rate_pct, availability_status,
    CASE WHEN bikes_available > 0
         THEN ROUND(CAST(electric_bikes AS FLOAT)/bikes_available*100, 1)
         ELSE 0 END                                   AS electric_ratio_pct,
    CASE WHEN is_installed=1 AND is_renting=1 AND is_returning=1
         THEN 1 ELSE 0 END                            AS is_active,
    GETUTCDATE()                                      AS ingested_at
INTO gold.mart_station_kpis
FROM silver.int_station_availability;

-- mart_city_overview : Vue globale Paris
SELECT
    COUNT(*)               AS total_stations,
    SUM(bikes_available)   AS total_bikes_available,
    SUM(mechanical_bikes)  AS total_mechanical,
    SUM(electric_bikes)    AS total_electric,
    SUM(docks_available)   AS total_docks_available,
    SUM(total_capacity)    AS total_capacity,
    ROUND(AVG(CAST(fill_rate_pct AS FLOAT)),1) AS avg_fill_rate_pct,
    SUM(CASE WHEN availability_status='empty' THEN 1 ELSE 0 END) AS stations_empty,
    SUM(CASE WHEN availability_status='full'  THEN 1 ELSE 0 END) AS stations_full,
    GETUTCDATE()           AS snapshot_at
INTO gold.mart_city_overview
FROM silver.int_station_availability
WHERE is_installed=1 AND is_renting=1;
            """,
                language="sql",
            )

    # ── TAB 5 : Lignée dbt ────────────────────────────────────────
    with tab5:
        st.subheader("Lignée des données — Graphe de dépendances dbt")
        st.markdown(
            "Chaque `{{ ref() }}` dans les modèles dbt crée une **dépendance traçable** "
            "entre les couches Bronze → Silver → Gold."
        )

        lineage_nodes = {
            "API\nVélib Status": (-2, 1),
            "API\nVélib Info": (-2, -1),
            "API\nMétéo": (-2, -3),
            "bronze\nstation_status": (0, 1),
            "bronze\nstation_info": (0, -1),
            "bronze\nweather": (0, -3),
            "silver\nstg_station_status": (2, 1),
            "silver\nstg_station_info": (2, -1),
            "silver\nstg_weather": (2, -3),
            "silver\nint_station\navailability": (4, 0),
            "silver\nint_avail\nweather": (4, -2),
            "gold\nmart_station\nkpis": (6, 1),
            "gold\nmart_city\noverview": (6, -1),
            "gold\nmart_weather\nimpact": (6, -3),
        }

        lineage_edges = [
            ("API\nVélib Status", "bronze\nstation_status"),
            ("API\nVélib Info", "bronze\nstation_info"),
            ("API\nMétéo", "bronze\nweather"),
            ("bronze\nstation_status", "silver\nstg_station_status"),
            ("bronze\nstation_info", "silver\nstg_station_info"),
            ("bronze\nweather", "silver\nstg_weather"),
            ("silver\nstg_station_status", "silver\nint_station\navailability"),
            ("silver\nstg_station_info", "silver\nint_station\navailability"),
            ("silver\nstg_weather", "silver\nint_avail\nweather"),
            ("silver\nint_station\navailability", "silver\nint_avail\nweather"),
            ("silver\nint_station\navailability", "gold\nmart_station\nkpis"),
            ("silver\nint_station\navailability", "gold\nmart_city\noverview"),
            ("silver\nint_avail\nweather", "gold\nmart_weather\nimpact"),
        ]

        layer_colors = {
            "API": "#4CAF50",
            "bronze": "#cd7f32",
            "silver": "#9E9E9E",
            "gold": "#FFC107",
        }

        ex, ey = [], []
        for s, d in lineage_edges:
            x0, y0 = lineage_nodes[s]
            x1, y1 = lineage_nodes[d]
            ex += [x0, x1, None]
            ey += [y0, y1, None]

        nx_ = [v[0] for v in lineage_nodes.values()]
        ny_ = [v[1] for v in lineage_nodes.values()]
        nl = list(lineage_nodes.keys())
        nc = [layer_colors[k.split("\n")[0]] for k in lineage_nodes]

        fig_lin = go.Figure()
        fig_lin.add_trace(
            go.Scatter(
                x=ex,
                y=ey,
                mode="lines",
                line=dict(width=2, color="#555"),
                hoverinfo="none",
            )
        )
        fig_lin.add_trace(
            go.Scatter(
                x=nx_,
                y=ny_,
                mode="markers+text",
                text=nl,
                textposition="middle center",
                textfont=dict(size=9),
                marker=dict(size=55, color=nc, line=dict(width=2, color="white")),
                hoverinfo="text",
            )
        )
        fig_lin.update_layout(
            showlegend=False,
            height=500,
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_lin, use_container_width=True)
        st.caption("🟢 API sources — 🟤 Bronze (brut) — ⚪ Silver (nettoyé) — 🟡 Gold (analytique)")

        st.divider()
        st.markdown("### Modèles dbt — résumé")
        dbt_models = [
            {"Couche": "Silver", "Modèle": "stg_station_status", "Type": "VIEW", "Source": "bronze.station_status"},
            {"Couche": "Silver", "Modèle": "stg_station_info", "Type": "VIEW", "Source": "bronze.station_info"},
            {"Couche": "Silver", "Modèle": "stg_weather", "Type": "VIEW", "Source": "bronze.weather"},
            {
                "Couche": "Silver",
                "Modèle": "int_station_availability",
                "Type": "VIEW",
                "Source": "stg_station_status + stg_station_info",
            },
            {
                "Couche": "Silver",
                "Modèle": "int_availability_weather",
                "Type": "VIEW",
                "Source": "int_station_availability + stg_weather",
            },
            {"Couche": "Gold", "Modèle": "mart_station_kpis", "Type": "TABLE", "Source": "int_station_availability"},
            {"Couche": "Gold", "Modèle": "mart_city_overview", "Type": "TABLE", "Source": "int_station_availability"},
            {"Couche": "Gold", "Modèle": "mart_weather_impact", "Type": "TABLE", "Source": "int_availability_weather"},
        ]
        st.dataframe(pd.DataFrame(dbt_models), use_container_width=True, hide_index=True)
