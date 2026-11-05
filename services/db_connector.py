import sqlite3
import pandas as pd
import geopandas as gpd

def load_db_data(db_path, start_time, end_time):
    conn = sqlite3.connect(db_path)
    query = """
        SELECT latitude, longitude, get_at, WIPS as wips, road_surface, image_path
        FROM pointed_road_data
        WHERE get_at >= ? AND get_at <= ?
    """
    df_obs = pd.read_sql_query(query, conn, params=(start_time, end_time))
    conn.close()
    
    if len(df_obs) == 0:
        return None

    return gpd.GeoDataFrame(
        df_obs,
        geometry=gpd.points_from_xy(df_obs.longitude, df_obs.latitude),
        crs="EPSG:4326"
    )