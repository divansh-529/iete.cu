import { Link } from "react-router";
import type { ChartNode } from "../../api/types";
import { cx } from "../../components/ui";

interface TreeNode extends ChartNode {
  children: TreeNode[];
}

function buildTree(nodes: ChartNode[]): TreeNode[] {
  const byId = new Map<number, TreeNode>(nodes.map((n) => [n.position_id, { ...n, children: [] }]));
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    const parent = node.reports_to_position_id != null ? byId.get(node.reports_to_position_id) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  return roots;
}

/** Reporting-line tree. Vacant positions are highlighted. */
export function OrgChart({ nodes }: { nodes: ChartNode[] }) {
  const roots = buildTree(nodes);
  return (
    <div className="overflow-x-auto pb-2">
      <ul className="space-y-2">{roots.map((n) => <Branch key={n.position_id} node={n} />)}</ul>
    </div>
  );
}

function Branch({ node }: { node: TreeNode }) {
  const vacant = node.holders.length === 0;
  const partly = !vacant && node.holders.length < node.max_holders && node.max_holders <= 3;
  return (
    <li>
      <Link to={`/app/org/positions/${node.position_id}`}
            className={cx("flex w-full max-w-xs flex-col rounded-md border px-3 py-2 text-sm shadow-xs transition-colors",
              vacant ? "border-dashed border-amber-400 bg-amber-50 hover:bg-amber-100"
                : "border-slate-200 bg-white hover:border-brand-500")}>
        <span className="font-semibold text-slate-900">{node.title}</span>
        {node.department_name && <span className="text-xs text-slate-500">{node.department_name}</span>}
        <span className={cx("mt-1 text-xs", vacant ? "font-medium text-amber-800" : "text-slate-700")}>
          {vacant ? "Vacant" : node.holders.map((h) => h.full_name).join(", ")}
          {partly && <span className="text-slate-500"> · {node.max_holders - node.holders.length} open</span>}
        </span>
      </Link>
      {node.children.length > 0 && (
        <ul className="ml-2 mt-2 space-y-2 border-l-2 border-slate-200 pl-3 sm:ml-4 sm:pl-4">
          {node.children.map((c) => <Branch key={c.position_id} node={c} />)}
        </ul>
      )}
    </li>
  );
}
