from pydantic import BaseModel
from typing import List,Optional

class ChartSeries(BaseModel):
    name:str
    color:str
    values:List[float]

class ChartLegend(BaseModel):
    label:str
    color:str

class AxisMetaData(BaseModel):
    label:Optional[str]=None
    tick_values:List[float]=[]
    min_value:Optional[float]=None
    max_value:Optional[float]=None

class ChartMetadata(BaseModel):
    chart_type:str
    title:str
    x_axis:AxisMetaData
    y_axis:AxisMetaData
    categories:List[str]
    legend:List[ChartLegend]
    series:List[ChartSeries]
    highlighted_categories:List[str]=[]
    notes:List[str]=[]
    confidence:float=1.0

    

