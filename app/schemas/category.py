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
    applicability: str = "optional"
    sort_order: int
    options: list[str] | None = None
    item_schema: dict | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    parent_id: int | None
    priority: str = "P2"
    is_group: bool = False
    sort_order: int = 0
    enabled: bool = True
    product_count: int = 0
    total_products: int = 0
    spec_definitions: list[CategorySpecificationDefinitionRead] = Field(default_factory=list)
    children: list["CategoryRead"] = Field(default_factory=list)
