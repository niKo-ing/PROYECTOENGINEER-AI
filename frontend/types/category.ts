export interface CategoryRead {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
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
