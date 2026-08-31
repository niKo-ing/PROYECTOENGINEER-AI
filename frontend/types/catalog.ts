export interface FacetOption {
  value: string;
  count: number;
}

export interface FacetRange {
  minimum: number | null;
  maximum: number | null;
}

export interface CategoryFacetSpec {
  key: string;
  label: string;
  group: string;
  data_type: string;
  unit: string | null;
  filter_type: string;
  kind: "options" | "range";
  options: FacetOption[];
  range: FacetRange | null;
}

export interface CategoryFacets {
  category: string;
  total: number;
  brands: FacetOption[];
  price_range: FacetRange | null;
  specs: CategoryFacetSpec[];
}