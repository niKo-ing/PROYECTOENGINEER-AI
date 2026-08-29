export interface AdminSpecValue {
  id: number;
  product_id: number;
  product_name: string;
  category: string | null;
  definition_key: string;
  label: string;
  group: string;
  value: string;
  raw_value: string | null;
  source_type: string;
  source_name: string | null;
  source_url: string | null;
  extraction_method: string | null;
  verification_status: string;
  conflict_status: string;
  history_count: number;
}

export interface AdminSpecReviewResponse {
  items: AdminSpecValue[];
}

export interface AdminDashboardMetrics {
  products: number;
  offers: number;
  stores: number;
  specs_pending: number;
  conflicts: number;
  products_without_specs: number;
  products_unverified: number;
  products_verified: number;
}

export interface AdminActivityItem {
  id: number;
  action: string;
  product_id: number;
  product_name: string;
  label: string;
  group: string;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  incoming_value: Record<string, unknown> | null;
  source_type: string;
  changed_by: string | null;
  created_at: string;
}

export interface AdminDashboardResponse {
  metrics: AdminDashboardMetrics;
  recent_activity: AdminActivityItem[];
}
