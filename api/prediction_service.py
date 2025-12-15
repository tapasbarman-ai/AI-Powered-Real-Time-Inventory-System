from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow.sklearn
import pandas as pd
import os
import uvicorn
from typing import List, Optional

app = FastAPI(title="Demand Prediction Service", version="1.0")

class ForecastRequest(BaseModel):
    product_name: str
    days: int = 7

class DailyForecast(BaseModel):
    date: str
    predicted_demand: int

class ForecastResponse(BaseModel):
    product_name: str
    recommended_reorder: int
    forecasts: List[DailyForecast]

# Load models (cache them in memory)
models = {}

def get_model(product_name):
    # In a real scenario, load from MLflow registry or local storage
    # For this POC, we'll try to load local pickle files first
    model_path = f"models/{product_name.replace(' ', '_').replace('/', '_')}_prophet.pkl"
    
    if product_name not in models:
        try:
            import pickle
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    models[product_name] = pickle.load(f)
            else:
                return None
        except Exception as e:
            print(f"Error loading model for {product_name}: {e}")
            return None
            
    return models.get(product_name)

@app.post("/forecast", response_model=ForecastResponse)
async def get_forecast(request: ForecastRequest):
    model = get_model(request.product_name)
    
    if not model:
        # Fallback: return dummy data or error if model not trained yet
        # For POC stability, we'll return a heuristic-based forecast if model is missing
        # raising HTTPException(status_code=404, detail=f"Model not found for {request.product_name}")
        return ForecastResponse(
            product_name=request.product_name,
            recommended_reorder=50,  # Default safety stock
            forecasts=[]
        )
    
    try:
        # Create future dataframe
        future = model.make_future_dataframe(periods=request.days)
        forecast = model.predict(future)
        
        # Get last N days
        future_forecast = forecast.tail(request.days)
        
        results = []
        total_demand = 0
        
        for _, row in future_forecast.iterrows():
            daily_demand = max(0, int(row['yhat']))
            results.append(DailyForecast(
                date=row['ds'].strftime('%Y-%m-%d'),
                predicted_demand=daily_demand
            ))
            total_demand += daily_demand
            
        return ForecastResponse(
            product_name=request.product_name,
            recommended_reorder=total_demand,
            forecasts=results
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
