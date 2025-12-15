import streamlit as st
import pandas as pd
import psycopg2
import time
import plotly.express as px

st.set_page_config(page_title="📦 Inventory Dashboard", layout="wide")
st.title("📦 Real-Time Inventory Dashboard")

@st.cache_resource
def get_connection():
    return psycopg2.connect(
        dbname="inventorydb",
        user="postgres",
        password="postgres",
        host="localhost",
        port="5432"
    )

conn = get_connection()
REFRESH_INTERVAL = 1
st.caption(f"⏱️ Auto-refreshing every {REFRESH_INTERVAL} seconds...")
time.sleep(REFRESH_INTERVAL)


@st.cache_data(ttl=1)  # cached only for 1 second
def load_data():
    return pd.read_sql("SELECT * FROM stock ORDER BY product_name;", conn)

df = load_data()

st.subheader("📋 Current Inventory")
st.dataframe(df, use_container_width=True)

fig = px.bar(df, x='product_name', y='quantity', color='quantity', height=400)
st.plotly_chart(fig, use_container_width=True)

low_stock = df[df['quantity'] < 20]
if not low_stock.empty:
    st.error("⚠️ Low stock warning!")
    st.dataframe(low_stock, use_container_width=True)
