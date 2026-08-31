export interface CategorySpecDefinition {
  id: number;
  key: string;
  label: string;
  group: string;
  data_type: string;
  unit: string | null;
  filter_type: string;
  required: boolean;
  comparable: boolean;
  facetable: boolean;
  sort_order: number;
  options: string[] | null;
}

export interface CategoryRead {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
  priority: string;
  is_group: boolean;
  sort_order: number;
  enabled: boolean;
  product_count: number;
  total_products: number;
  spec_definitions: CategorySpecDefinition[];
  children: CategoryRead[];
}

export function flattenCategories(tree: CategoryRead[]): CategoryRead[] {
  const result: CategoryRead[] = [];
  for (const node of tree) {
    result.push(node);
    result.push(...flattenCategories(node.children));
  }
  return result;
}

export function findCategoryBySlug(root: CategoryRead, slug: string): CategoryRead | null {
  if (root.slug === slug) return root;
  for (const child of root.children) {
    const match = findCategoryBySlug(child, slug);
    if (match) return match;
  }
  return null;
}

/** Ancestors (root first) ending at the matching node. */
export function findCategoryChain(tree: CategoryRead[], slug: string): CategoryRead[] | null {
  for (const node of tree) {
    const chain = findPath(node, slug);
    if (chain) return chain;
  }
  return null;
}

function findPath(node: CategoryRead, slug: string): CategoryRead[] | null {
  if (node.slug === slug) return [node];
  for (const child of node.children) {
    const childPath = findPath(child, slug);
    if (childPath) return [node, ...childPath];
  }
  return null;
}

/** Top-level groups displayed on the home explorer, skipping pure wrapper nodes. */
export function mainGroups(tree: CategoryRead[]): CategoryRead[] {
  const enabled = tree.filter((node) => node.enabled);
  for (const root of enabled) {
    if (
      root.is_group &&
      root.product_count === 0 &&
      root.children.some((child) => child.is_group || child.children.length > 0)
    ) {
      return root.children.filter((child) => child.enabled);
    }
  }
  return enabled;
}

export function isLeafCategory(category: CategoryRead): boolean {
  return category.children.length === 0;
}