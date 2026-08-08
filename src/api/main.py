"""FastAPI application for the Ad-Challenge dashboard."""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime

from src.db.session import get_db, engine, Base
from src.db.models import Campaign, Creative, CreativeMetric, ModelBenchmark, FeatureImportance

app = FastAPI(title="Ad-Challenge API")

# Allow CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """Redirect to the interactive API documentation."""
    return RedirectResponse(url="/docs")


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get global stats for the dashboard hero section."""
    total_events = db.query(func.sum(CreativeMetric.n_impressions)).scalar() or 0
    total_creatives = db.query(Creative).count()
    total_campaigns = db.query(Campaign).count()
    
    # Get the latest multimodal R2 score
    mm_bench = db.query(ModelBenchmark).filter(ModelBenchmark.model_name == "multimodal").order_by(ModelBenchmark.run_timestamp.desc()).first()
    r2_score = mm_bench.r2 if mm_bench else 0.0

    return {
        "total_events": total_events,
        "total_creatives": total_creatives,
        "total_campaigns": total_campaigns,
        "multimodal_r2": round(r2_score, 4)
    }


@app.get("/api/benchmarks")
def get_benchmarks(db: Session = Depends(get_db)):
    """Get the latest benchmark results for all models."""
    # Find the latest timestamp
    latest_run = db.query(func.max(ModelBenchmark.run_timestamp)).scalar()
    if not latest_run:
        return {}

    benchmarks = db.query(ModelBenchmark).filter(ModelBenchmark.run_timestamp == latest_run).all()
    
    results = {}
    for b in benchmarks:
        results[b.model_name] = {
            "r2": round(b.r2, 4),
            "mae": round(b.mae, 4),
            "mape": round(b.mape, 2),
            "n_features": b.n_features
        }
        
    return results


@app.get("/api/features")
def get_features(db: Session = Depends(get_db)):
    """Get the top 10 features for the multimodal model."""
    latest_run = db.query(func.max(FeatureImportance.run_timestamp)).scalar()
    if not latest_run:
        return []

    features = db.query(FeatureImportance).filter(
        FeatureImportance.run_timestamp == latest_run,
        FeatureImportance.model_name == "multimodal"
    ).order_by(FeatureImportance.importance_score.desc()).limit(10).all()

    return [
        {
            "name": f.feature_name.replace("_", " ").title(),
            "importance": round(f.importance_score, 4),
            "category": f.category
        }
        for f in features
    ]


from pydantic import BaseModel

class PredictionRequest(BaseModel):
    device: str
    os: str
    region: str
    cpe: float
    brightness: float
    saturation: float
    colorfulness: float
    has_video: bool

@app.post("/api/predict")
def predict_performance(req: PredictionRequest):
    """
    Heuristic prediction endpoint. 
    In a true production setting, this would call the pickled LightGBM model.
    For this demo, we keep the heuristic logic that responds instantly.
    """
    base_er = 0.12
    
    # Contextual adjustments
    er = base_er
    if req.device == 'smartphone': er *= 1.15
    if req.os == 'iOS': er *= 1.08
    if req.region == 'USA': er *= 1.10
    
    er *= (1 - req.cpe * 0.3)  # higher CPE = lower ER
    
    # Visual adjustments
    er *= (0.8 + req.brightness * 0.004)
    er *= (0.85 + req.saturation * 0.003)
    er *= (0.9 + req.colorfulness * 0.002)
    
    if req.has_video: er *= 1.12
    
    ctr = er * 0.45  # Simplified relation
    
    # Tier logic
    tier = "avg"
    tier_label = "🟡 Average"
    if er < 0.08:
        tier = "low"
        tier_label = "🔴 Low"
    elif er > 0.15:
        tier = "top"
        tier_label = "⭐ Top Performer"
    elif er > 0.12:
        tier = "high"
        tier_label = "🟢 High"
        
    return {
        "er_percent": round(er * 100, 1),
        "ctr_percent": round(ctr * 100, 1),
        "tier": tier,
        "tier_label": tier_label
    }
