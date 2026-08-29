from pydantic import BaseModel, ConfigDict, Field


class CategorySpecificationDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    group: str
    data_type: str
    unit: str | None
    filter_type: str
    required: bool
    comparable: bool
    facetable: bool
    sort_order: int
    options: list[str] | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    parent_id: int | None
    priority: str
    is_group: bool
    spec_definitions: list[CategorySpecificationDefinitionRead] = Field(default_factory=list)
    children: list["CategoryRead"] = Field(default_factory=list)
