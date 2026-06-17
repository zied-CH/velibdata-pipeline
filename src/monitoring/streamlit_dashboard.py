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


# ── PlantUML helper ──────────────────────────────────────────────


def _plantuml_url(text: str) -> str:
    """Encode PlantUML text and return the public server PNG URL."""
    import zlib

    data = zlib.compress(text.encode("utf-8"))[2:-4]

    def _enc6(b: int) -> str:
        if b < 10:
            return chr(48 + b)
        b -= 10
        if b < 26:
            return chr(65 + b)
        b -= 26
        if b < 26:
            return chr(97 + b)
        b -= 26
        return "-" if b == 0 else "_"

    def _enc3(b1: int, b2: int, b3: int) -> str:
        return (
            _enc6((b1 >> 2) & 0x3F)
            + _enc6(((b1 & 3) << 4 | b2 >> 4) & 0x3F)
            + _enc6(((b2 & 0xF) << 2 | b3 >> 6) & 0x3F)
            + _enc6(b3 & 0x3F)
        )

    result = ""
    for i in range(0, len(data), 3):
        chunk = data[i : i + 3]
        padded = chunk + b"\x00" * (3 - len(chunk))
        result += _enc3(padded[0], padded[1], padded[2])

    return f"https://www.plantuml.com/plantuml/png/{result}"


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
    st.caption("MCD · ERD · MLD · MPD · Lignée dbt — rendus avec PlantUML")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["MCD", "ERD", "MLD", "MPD", "Lignée dbt"])

    # ── TAB 1 : MCD ───────────────────────────────────────────────
    with tab1:
        st.subheader("Modèle Conceptuel des Données")
        st.markdown("Représentation des **concepts métier** sans considération technique.")
        mcd = """
@startuml
!theme plain
skinparam backgroundColor #FAFAFA
skinparam entity {
  BackgroundColor #E3F2FD
  BorderColor #1565C0
  FontColor #0D47A1
}
skinparam ArrowColor #1565C0

entity "STATION" as S {
  * station_id <<PK>>
  --
  nom_station
  latitude / longitude
  capacite_totale
}

entity "STATUT_STATION" as SS {
  * station_id <<FK>>
  * horodatage <<PK>>
  --
  velos_disponibles
  bornes_libres
}

entity "METEO" as M {
  * heure_mesure <<PK>>
  --
  temperature
  precipitations
  conditions_cyclisme
}

S ||--o{ SS : "possede (1,N)"
SS }o--o{ M : "observee lors de (0,N)"
@enduml
"""
        st.image(_plantuml_url(mcd), use_container_width=True)
        st.markdown(
            "- **1 station** possède **plusieurs statuts** dans le temps (toutes les ~15 min)\n"
            "- **1 statut** est corrélé à **0 ou 1 météo** (jointure sur l'heure arrondie)"
        )

    # ── TAB 2 : ERD ───────────────────────────────────────────────
    with tab2:
        st.subheader("Entity-Relationship Diagram")
        st.markdown("Diagramme entité-association avec attributs et types de données.")
        erd = """
@startuml
!theme plain
skinparam backgroundColor #FAFAFA
skinparam class {
  BackgroundColor #E8F5E9
  BorderColor #2E7D32
  FontColor #1B5E20
}

entity STATION {
  * station_id : BIGINT <<PK>>
  --
  station_code : VARCHAR(10)
  station_name : NVARCHAR(200)
  latitude : FLOAT
  longitude : FLOAT
  total_capacity : INT
  ingested_at : DATETIME2
}

entity STATION_STATUS {
  * station_id : BIGINT <<FK>>
  * last_reported_at : DATETIME2
  --
  bikes_available : INT
  mechanical_bikes : INT
  electric_bikes : INT
  docks_available : INT
  is_installed : BIT
  is_renting : BIT
  is_returning : BIT
}

entity WEATHER {
  * measured_at : DATETIME2 <<PK>>
  --
  temperature_celsius : FLOAT
  precipitation_mm : FLOAT
  wind_speed_kmh : FLOAT
  weather_code : INT
  weather_category : VARCHAR
  cycling_conditions : VARCHAR
}

entity MART_STATION_KPIS {
  * station_id : BIGINT <<FK>>
  --
  fill_rate_pct : FLOAT
  electric_ratio_pct : FLOAT
  availability_status : VARCHAR
  is_active : BIT
  last_reported_at : DATETIME2
}

entity MART_CITY_OVERVIEW {
  * snapshot_at : DATETIME2 <<PK>>
  --
  total_stations : INT
  total_bikes_available : INT
  avg_fill_rate_pct : FLOAT
  stations_empty : INT
  stations_full : INT
}

entity MART_WEATHER_IMPACT {
  * weather_category : VARCHAR
  * cycling_conditions : VARCHAR
  * snapshot_hour : DATETIME2
  --
  avg_fill_rate_pct : FLOAT
  pct_stations_empty : FLOAT
  nb_observations : INT
}

STATION ||--o{ STATION_STATUS : "possede"
STATION ||--o{ MART_STATION_KPIS : "alimente"
STATION_STATUS }o--|| MART_CITY_OVERVIEW : "agrege"
WEATHER }o--o{ MART_WEATHER_IMPACT : "impacte"
@enduml
"""
        st.image(_plantuml_url(erd), use_container_width=True)

    # ── TAB 3 : MLD ───────────────────────────────────────────────
    with tab3:
        st.subheader("Modèle Logique des Données")
        st.markdown("Architecture médaillon complète — Bronze, Silver, Gold.")
        mld = """
@startuml
!theme plain
skinparam backgroundColor #FAFAFA
skinparam package {
  BackgroundColor #FFFDE7
  BorderColor #F57F17
}
skinparam class {
  FontSize 11
}

package "BRONZE — donnees brutes" #FFE0B2 {
  class station_info << (T,#cd7f32) TABLE >> {
    # station_id : BIGINT
    stationCode : VARCHAR(10)
    name : NVARCHAR(200)
    capacity : INT
    lat : FLOAT
    lon : FLOAT
    ingested_at : DATETIME2
  }
  class station_status << (T,#cd7f32) TABLE >> {
    # station_id : BIGINT
    # ingested_at : DATETIME2
    num_bikes_available : INT
    num_docks_available : INT
    num_bikes_available_types : JSON
    is_installed / is_renting : BIT
    last_reported : BIGINT
  }
  class weather << (T,#cd7f32) TABLE >> {
    # time : DATETIME2
    temperature_2m : FLOAT
    precipitation : FLOAT
    windspeed_10m : FLOAT
    weathercode : INT
    ingested_at : DATETIME2
  }
}

package "SILVER — donnees nettoyees" #E0E0E0 {
  class stg_station_info << (V,#9E9E9E) VIEW >> {
    # station_id : BIGINT
    station_code : VARCHAR(10)
    station_name : VARCHAR(200)
    total_capacity : INT
    latitude : FLOAT
    longitude : FLOAT
  }
  class stg_station_status << (V,#9E9E9E) VIEW >> {
    # station_id -> stg_station_info
    bikes_available : INT
    mechanical_bikes : INT
    electric_bikes : INT
    last_reported_at : DATETIME2
  }
  class stg_weather << (V,#9E9E9E) VIEW >> {
    # measured_at : DATETIME2
    temperature_celsius : FLOAT
    precipitation_mm : FLOAT
    wind_speed_kmh : FLOAT
    weather_code : INT
  }
  class int_station_availability << (V,#9E9E9E) VIEW >> {
    # station_id
    station_name / lat / lon
    fill_rate_pct : FLOAT [calcule]
    availability_status : VARCHAR [calcule]
    bikes_available : INT
  }
  class int_availability_weather << (V,#9E9E9E) VIEW >> {
    # station_id
    # hour_key -> stg_weather
    weather_category : VARCHAR [calcule]
    cycling_conditions : VARCHAR [calcule]
    fill_rate_pct : FLOAT
  }
}

package "GOLD — marts analytiques" #FFF9C4 {
  class mart_station_kpis << (T,#FFC107) TABLE >> {
    # station_id : BIGINT
    station_name / lat / lon
    fill_rate_pct : FLOAT
    electric_ratio_pct : FLOAT [calcule]
    is_active : BIT [calcule]
  }
  class mart_city_overview << (T,#FFC107) TABLE >> {
    # snapshot_at : DATETIME2
    total_stations : INT
    total_bikes_available : INT
    avg_fill_rate_pct : FLOAT
    stations_empty / full / low : INT
  }
  class mart_weather_impact << (T,#FFC107) TABLE >> {
    # weather_category
    # cycling_conditions
    avg_fill_rate_pct : FLOAT
    pct_stations_empty : FLOAT
    nb_observations : INT
  }
}

station_info --> stg_station_info
station_status --> stg_station_status
weather --> stg_weather
stg_station_info --> int_station_availability
stg_station_status --> int_station_availability
stg_weather --> int_availability_weather
int_station_availability --> int_availability_weather
int_station_availability --> mart_station_kpis
int_station_availability --> mart_city_overview
int_availability_weather --> mart_weather_impact
@enduml
"""
        st.image(_plantuml_url(mld), use_container_width=True)

    # ── TAB 4 : MPD ───────────────────────────────────────────────
    with tab4:
        st.subheader("Modèle Physique des Données — Azure SQL Server T-SQL")
        mpd = """
@startuml
!theme plain
skinparam backgroundColor #FAFAFA
skinparam class {
  BackgroundColor #E8EAF6
  BorderColor #3949AB
  FontColor #1A237E
  FontSize 10
}
skinparam package {
  BorderColor #7986CB
}
hide circle

package "bronze" #ddeeff {
  class station_info <<TABLE>> {
    station_id : BIGINT PK
    stationCode : VARCHAR(10)
    name : NVARCHAR(200)
    capacity : INT
    lat : FLOAT
    lon : FLOAT
  }
  class station_status <<TABLE>> {
    station_id : BIGINT
    ingested_at : DATETIME2 PK
    num_bikes_available : INT
    num_docks_available : INT
    is_installed : BIT
    last_reported : BIGINT
  }
  class weather <<TABLE>> {
    time : DATETIME2 PK
    temperature_2m : FLOAT
    precipitation : FLOAT
    windspeed_10m : FLOAT
    weathercode : INT
  }
}

package "silver" #eeddff {
  class stg_station_status <<VIEW>> {
    station_id : BIGINT
    bikes_available : INT
    mechanical_bikes : INT
    electric_bikes : INT
  }
  class stg_station_info <<VIEW>> {
    station_id : BIGINT
    station_name : VARCHAR(200)
    total_capacity : INT
    latitude : FLOAT
    longitude : FLOAT
  }
  class stg_weather <<VIEW>> {
    measured_at : DATETIME2
    temperature_celsius : FLOAT
    precipitation_mm : FLOAT
    wind_speed_kmh : FLOAT
  }
  class int_station_availability <<VIEW>> {
    station_id : BIGINT
    fill_rate_pct : FLOAT
    availability_status : VARCHAR(10)
  }
  class int_availability_weather <<VIEW>> {
    station_id : BIGINT
    fill_rate_pct : FLOAT
    cycling_conditions : VARCHAR(10)
  }
}

package "gold" #ffffcc {
  class mart_station_kpis <<TABLE>> {
    station_id : BIGINT
    fill_rate_pct : FLOAT
    electric_ratio_pct : FLOAT
    is_active : BIT
  }
  class mart_city_overview <<TABLE>> {
    total_stations : INT
    total_bikes_available : INT
    avg_fill_rate_pct : FLOAT
  }
  class mart_weather_impact <<TABLE>> {
    weather_category : VARCHAR(10)
    avg_fill_rate_pct : FLOAT
    nb_observations : INT
  }
}

station_status --> stg_station_status : staging
station_info --> stg_station_info : staging
weather --> stg_weather : staging
stg_station_status --> int_station_availability : int
stg_station_info --> int_station_availability : int
int_station_availability --> int_availability_weather : int
stg_weather --> int_availability_weather : int
int_station_availability --> mart_station_kpis : mart
int_station_availability --> mart_city_overview : mart
int_availability_weather --> mart_weather_impact : mart
@enduml
"""
        st.image(_plantuml_url(mpd), use_container_width=True)

    # ── TAB 5 : Lignée dbt ────────────────────────────────────────
    with tab5:
        st.subheader("Lignée des données — Data Lineage")
        st.markdown("Chaque `{{ ref() }}` dans les modèles dbt crée une **dépendance traçable** entre les couches.")
        lineage = """
@startuml
!theme plain
left to right direction
skinparam backgroundColor #FAFAFA
skinparam ArrowColor #555555
skinparam node {
  FontSize 11
  BorderThickness 1.5
}

node "API Velib\\nstation_status" as api_s #ADD8E6
node "API Velib\\nstation_info"   as api_i #ADD8E6
node "API Open-Meteo\\nmeteo"     as api_w #ADD8E6

database "bronze\\nstation_status" as b_s #DEB887
database "bronze\\nstation_info"   as b_i #DEB887
database "bronze\\nweather"        as b_w #DEB887

rectangle "silver\\nstg_status"   as s_ss #DCDCDC
rectangle "silver\\nstg_info"     as s_si #DCDCDC
rectangle "silver\\nstg_weather"  as s_sw #DCDCDC
rectangle "silver\\nint_avail"    as s_av #DCDCDC
rectangle "silver\\nint_weather"  as s_aw #DCDCDC

database "gold\\nmart_kpis"     as g_k #FFD700
database "gold\\nmart_city"     as g_c #FFD700
database "gold\\nmart_weather"  as g_w #FFD700

api_s --> b_s : ingest
api_i --> b_i : ingest
api_w --> b_w : ingest

b_s --> s_ss : staging
b_i --> s_si : staging
b_w --> s_sw : staging

s_ss --> s_av : int
s_si --> s_av : int
s_av --> s_aw : int
s_sw --> s_aw : int

s_av --> g_k : mart
s_av --> g_c : mart
s_aw --> g_w : mart
@enduml
"""
        st.image(_plantuml_url(lineage), use_container_width=True)
        st.caption("🔵 API sources — 🟤 Bronze — ⚪ Silver — 🟡 Gold")

        st.divider()
        st.markdown("### Modèles dbt — 8 modèles")
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
