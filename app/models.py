from sqlalchemy import Column, Integer, Float
from sqlalchemy.sql import expression
from .db import Base


class PopulationPoint(Base):
    __tablename__ = "population_density_points"

    id = Column(Integer, primary_key=True, index=True)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    population_density = Column(Float, nullable=True)
