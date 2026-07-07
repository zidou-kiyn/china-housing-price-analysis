from pydantic import BaseModel


class CityOut(BaseModel):
    id: int
    name: str
    code: str

    model_config = {"from_attributes": True}


class DistrictOut(BaseModel):
    id: int
    name: str
    code: str

    model_config = {"from_attributes": True}
