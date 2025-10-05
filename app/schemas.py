from pydantic import BaseModel


class PopulationPointOut(BaseModel):
    id: int
    longitude: float
    latitude: float
    population_density: float | None

    class Config:
        orm_mode = True
