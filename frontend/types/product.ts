export interface SpecItem {
  label: string;
  value: string;
}

export interface SpecSection {
  title: string;
  items: SpecItem[];
}

export interface ProductSpecs {
  highlights: string[];
  sections: SpecSection[];
}

export interface CanonicalSpecItem {
  key: string;
  label: string;
  value: string;
  raw_value: string | null;
  unit: string | null;
  value_kind: string | null;
  source_type: string | null;
  source_name: string | null;
  verification_status: string | null;
  conflict_status: string | null;
}

export interface CanonicalSpecSection {
  title: string;
  items: CanonicalSpecItem[];
}

export interface CanonicalProductSpecs {
  sections: CanonicalSpecSection[];
}

export interface ProductRead {
  id: number;
  name: string;
  category: string;
  price_clp: number;
  brand: string | null;
  description: string | null;
  description_ai: string | null;
  specs: ProductSpecs | null;
  canonical_specs: CanonicalProductSpecs | null;
  rating: number | null;
  image_url: string | null;
  images: string[];
  created_at: string;
  lowest_price: number | null;
  lowest_price_store: string | null;
  offer_count: number;
}

export interface ProductSearchResult {
  items: ProductRead[];
  total: number;
}

export interface ProductSearchParams {
  query?: string;
  category?: string;
  brand?: string;
  min_price_clp?: number;
  max_price_clp?: number;
  limit?: number;
  offset?: number;
}
