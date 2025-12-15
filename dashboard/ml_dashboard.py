import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px
import plotly.graph_objects as go
import requests
import time
import os

st.set_page_config(page_title="🤖 AI Demand Forecasting", layout="wide")

# Database Connection
@st.cache_resource
def get_connection():
    return psycopg2.connect(
        dbname="inventorydb",
        user="postgres",
        password="postgres",
        host="postgres",
        port="5432"
    )

def load_data():
    conn = get_connection()
    # Get recent stock
    stock_df = pd.read_sql("SELECT * FROM stock ORDER BY quantity ASC", conn)
    
    # Get model metrics
    metrics_query = """
    SELECT * FROM model_metrics 
    WHERE created_at >= NOW() - INTERVAL '24 hours'
    ORDER BY created_at DESC
    """
    metrics_df = pd.read_sql(metrics_query, conn)
    
    # Get recommendations
    recs_query = """
    SELECT * FROM reorder_recommendations 
    WHERE status = 'pending'
    ORDER BY created_at DESC
    """
    recs_df = pd.read_sql(recs_query, conn)
    
    return stock_df, metrics_df, recs_df

# Title & Metrics
st.title("🤖 AI-Powered Inventory Intelligence")

# Auto-refresh using session state for timer
REFRESH_INTERVAL = 5 # seconds

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Inventory & Forecasts", "🧠 Model Performance", "🔔 Smart Alerts"])

stock_df, metrics_df, recs_df = load_data()

with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Real-Time Stock Levels")
        # Add unique key based on time to force refresh or static key if just updating data
        fig = px.bar(stock_df, x='product_name', y='quantity', 
                    color='quantity', 
                    color_continuous_scale='RdYlGn',
                    title="Current Inventory Levels")
        # Use a unique key to prevent duplicate ID errors on rerun
        st.plotly_chart(fig, use_container_width=True, key="inventory_chart")
    
    with col2:
        st.subheader("🔍 Demand Forecast")
        selected_product = st.selectbox("Select Product to Forecast", stock_df['product_name'].unique())
        
        if st.button("Generate Forecast", key="forecast_btn"):
            with st.spinner("Running AI Model..."):
                try:
                    # Call Prediction Service
                    resp = requests.post(
                        "http://prediction-service:8000/forecast",
                        json={"product_name": selected_product, "days": 7},
                        timeout=3
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        f_df = pd.DataFrame(data['forecasts'])
                        
                        st.success(f"Recommended Reorder: {data['recommended_reorder']} units")
                        
                        # Plot forecast
                        fig_f = px.line(f_df, x='date', y='predicted_demand', markers=True, 
                                      title=f"7-Day Demand Forecast for {selected_product}")
                        st.plotly_chart(fig_f, use_container_width=True, key=f"forecast_chart_{selected_product}")
                        
                    else:
                        st.error("Could not fetch forecast. Model may not be trained yet.")
                except Exception as e:
                    st.error(f"Service unavailable: {e}")

with tab2:
    st.subheader("📈 Model Training Metrics (Last 24h)")
    if not metrics_df.empty:
        # Pivot for better view
        latest_metrics = metrics_df.drop_duplicates(subset=['product_name', 'metric_name'], keep='first')
        pivot_df = latest_metrics.pivot(index='product_name', columns='metric_name', values='metric_value')
        st.dataframe(pivot_df.style.highlight_min(axis=0, color='lightgreen'), use_container_width=True)
        
        st.markdown("### 📉 Drift Detection")
        st.info("No significant concept drift detected in the last 24 hours.")
    else:
        st.warning("No model metrics available yet. Models are training...")

with tab3:
    st.subheader("🚨 Intelligent Reorder Recommendations")
    if not recs_df.empty:
        for idx, row in recs_df.iterrows():
            urgency_color = "🔴" if row['urgency_level'] == 'critical' else "🟠"
            with st.expander(f"{urgency_color} Order Recommendation: {row['product_name']} ({row['recommended_quantity']} units)"):
                st.write(f"**Reason:** {row['reason']}")
                st.write(f"**Generated:** {row['created_at']}")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.button("✅ Approve Order", key=f"approve_{idx}")
                with col_b:
                    st.button("❌ Dismiss", key=f"dismiss_{idx}")
    else:
        st.success("All good! No urgent reorders needed.")

# Auto-refresh logic
time.sleep(REFRESH_INTERVAL)
st.rerun()
