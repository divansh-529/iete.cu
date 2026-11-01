import { useState } from "react";
import { Link } from "react-router";
import type { ChartNode } from "../../api/types";
import { Badge, cx } from "../../components/ui";
import { AddToChartModal, DeletePositionModal } from "./modals";

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

/** Reporting-line tree. Vacant positions are highlighted; `editable` adds the Chairperson's add and delete. */
export function OrgChart({ nodes, editable = false }: { nodes: ChartNode[]; editable?: boolean }) {
  const roots = buildTree(nodes);
  const [adding, setAdding] = useState<TreeNode | null>(null);
  const [deleting, setDeleting] = useState<TreeNode | null>(null);
  const actions = editable ? { onAdd: setAdding, onDelete: setDeleting } : undefined;
  return (
    <div className="overflow-x-auto pb-2">
      <ul className="space-y-2">{roots.map((n) => <Branch key={n.position_id} node={n} actions={actions} />)}</ul>
      {adding && <AddToChartModal parent={{ id: adding.position_id, title: adding.title }} onClose={() => setAdding(null)} />}
      {deleting && (
        <DeletePositionModal position={{ id: deleting.position_id, title: deleting.title, holderCount: deleting.holders.length }}
                             onClose={() => setDeleting(null)} />
      )}
    </div>
  );
}

function Branch({ node, actions }: { node: TreeNode; actions?: { onAdd: (n: TreeNode) => void; onDelete: (n: TreeNode) => void } }) {
  const vacant = node.holders.length === 0 && !node.is_category;
  const partly = !vacant && node.holders.length < node.max_holders && node.max_holders <= 3;
  return (
    <li>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Link to={`/app/org/positions/${node.position_id}`}
              className={cx("flex w-full max-w-xs flex-col rounded-md border px-3 py-2 text-sm shadow-xs transition-colors",
                node.is_category ? "border-slate-300 bg-slate-100 hover:border-brand-500"
                  : vacant ? "border-dashed border-amber-400 bg-amber-50 hover:bg-amber-100"
                  : "border-slate-200 bg-white hover:border-brand-500")}>
          <span className="flex items-center justify-between gap-2 font-semibold text-slate-900">
            {node.title}
            {node.is_category && <Badge>Category</Badge>}
          </span>
          {node.department_name && <span className="text-xs text-slate-500">{node.department_name}</span>}
          {!node.is_category && (
            <span className={cx("mt-1 text-xs", vacant ? "font-medium text-amber-800" : "text-slate-700")}>
              {vacant ? "Vacant" : node.holders.map((h) => h.full_name).join(", ")}
              {partly && <span className="text-slate-500"> · {node.max_holders - node.holders.length} open</span>}
            </span>
          )}
        </Link>
        {actions && (
          <span className="flex gap-1 text-xs font-medium">
            <button onClick={() => actions.onAdd(node)} aria-label={`Add under ${node.title}`}
                    className="rounded-md px-2 py-1 text-brand-700 hover:bg-brand-50">+ Add under</button>
            <button onClick={() => actions.onDelete(node)} aria-label={`Delete ${node.title}`}
                    className="rounded-md px-2 py-1 text-red-700 hover:bg-red-50">Delete</button>
          </span>
        )}
      </div>
      {node.children.length > 0 && (
        <ul className="ml-2 mt-2 space-y-2 border-l-2 border-slate-200 pl-3 sm:ml-4 sm:pl-4">
          {node.children.map((c) => <Branch key={c.position_id} node={c} actions={actions} />)}
        </ul>
      )}
    </li>
  );
}
