from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from . import models, schemas
from .db import engine, Base, get_db

# Create tables if they don't exist (SQLite)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Population Density API")


@app.get("/points/", response_model=List[schemas.PopulationPointOut])
def read_points(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(100, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Return population points within a bounding box."""
    if min_lon > max_lon or min_lat > max_lat:
        raise HTTPException(status_code=400, detail="Invalid bbox coordinates")

    query = (
        db.query(models.PopulationPoint)
        .filter(models.PopulationPoint.longitude >= min_lon)
        .filter(models.PopulationPoint.longitude <= max_lon)
        .filter(models.PopulationPoint.latitude >= min_lat)
        .filter(models.PopulationPoint.latitude <= max_lat)
        .limit(limit)
    )

    return query.all()


@app.get("/points/nearby/", response_model=List[schemas.PopulationPointOut])
def read_points_near(
    lon: float = Query(...),
    lat: float = Query(...),
    radius_km: float = Query(5.0, gt=0.0),
    limit: int = Query(100, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Return points within a radius (approximate, using simple bbox as approximation)."""
    # Simple approximation: convert km to degrees (rough)
    degs = radius_km / 111.0
    min_lon, max_lon = lon - degs, lon + degs
    min_lat, max_lat = lat - degs, lat + degs

    return read_points(min_lon, min_lat, max_lon, max_lat, limit, db)
