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

export interface ProductRead {
  id: number;
  name: string;
  category: string;
  price_clp: number;
  brand: string | null;
  description: string | null;
  description_ai: string | null;
  specs: ProductSpecs | null;
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
