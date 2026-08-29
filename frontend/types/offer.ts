export interface StoreSummary {
  id: number;
  name: string;
  domain: string;
  store_type: string;
}

export interface StoreOfferRead {
  id: number;
  store: StoreSummary;
  url: string;
  price: number;
  original_price: number | null;
  currency: string;
  stock_status: string;
  availability: boolean;
  payment_condition: string | null;
  seller_name: string | null;
  last_checked_at: string;
}

export interface PriceHistoryRead {
  id: number;
  price: number;
  original_price: number | null;
  currency: string;
  observed_at: string;
}
