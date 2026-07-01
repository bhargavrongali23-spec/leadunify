import { useState, useEffect } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  Plus,
  Filter,
  Trash2,
  MoreVertical,
  Loader2,
  X,
  Type,
  ListOrdered,
  CheckSquare,
} from "lucide-react";
import { toast } from "sonner";

/**
 * Custom columns manager for a single campaign.
 * Renders:
 *   1. "Add column" button (opens dialog)
 *   2. For each column, a table header with filter icon
 *   3. For each cell, an inline editor (text / select / checkbox)
 */
export function AddColumnButton({ campaignId, onAdded }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("select");
  const [optionsText, setOptionsText] = useState("Sent\nNot sent");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim()) {
      toast.error("Column name required");
      return;
    }
    const options =
      kind === "select"
        ? optionsText
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean)
        : [];
    if (kind === "select" && options.length === 0) {
      toast.error("Add at least one option");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/campaigns/${campaignId}/columns`, {
        name: name.trim(),
        kind,
        options,
      });
      toast.success("Column added");
      setName("");
      setOptionsText("Sent\nNot sent");
      setKind("select");
      setOpen(false);
      onAdded?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        size="sm"
        variant="outline"
        className="text-xs h-8"
        onClick={() => setOpen(true)}
        data-testid="add-column-btn"
      >
        <Plus className="w-3 h-3 mr-1" /> Add column
      </Button>
      <DialogContent data-testid="add-column-dialog">
        <DialogHeader>
          <DialogTitle>Add a custom column</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="col-name">Column name</Label>
            <Input
              id="col-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='e.g. "Email 1 status" or "Meeting set"'
              className="mt-1.5"
              data-testid="new-column-name-input"
              autoFocus
            />
          </div>
          <div>
            <Label>Field type</Label>
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {[
                { k: "select", icon: ListOrdered, label: "Choices" },
                { k: "text", icon: Type, label: "Free text" },
                { k: "checkbox", icon: CheckSquare, label: "Checkbox" },
              ].map(({ k, icon: Icon, label }) => (
                <button
                  key={k}
                  type="button"
                  data-testid={`col-kind-${k}`}
                  onClick={() => setKind(k)}
                  className={`border rounded-md p-2.5 text-left transition-colors ${
                    kind === k
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <Icon className="w-4 h-4 text-indigo-600 mb-1" />
                  <div className="text-[12.5px] font-medium">{label}</div>
                </button>
              ))}
            </div>
          </div>
          {kind === "select" && (
            <div>
              <Label htmlFor="col-opts">Options (one per line)</Label>
              <textarea
                id="col-opts"
                value={optionsText}
                onChange={(e) => setOptionsText(e.target.value)}
                rows={5}
                className="mt-1.5 w-full text-sm border border-slate-200 rounded-md px-3 py-2 text-mono focus:border-indigo-400 outline-none"
                placeholder="Sent&#10;Not sent&#10;Bounced"
                data-testid="new-column-options-input"
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={saving || !name.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
            data-testid="create-column-btn"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Add column"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Header cell for a custom column — shows the label + a filter popover with
 * value counts (Excel-style). Also has a menu to delete the column.
 */
export function CustomColumnHeader({
  campaignId,
  column,
  valueCounts,
  activeValues,
  onFilterChange,
  onDeleted,
}) {
  const [open, setOpen] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const counts = valueCounts || [];
  const hasFilter = (activeValues || []).length > 0;

  const toggle = (val) => {
    const active = new Set(activeValues || []);
    if (active.has(val)) active.delete(val);
    else active.add(val);
    onFilterChange?.(Array.from(active));
  };

  const clear = () => onFilterChange?.([]);

  const doDelete = async () => {
    try {
      await api.delete(`/campaigns/${campaignId}/columns/${column.id}`);
      toast.success("Column removed");
      setConfirmDel(false);
      onDeleted?.();
    } catch (_e) {
      toast.error("Delete failed");
    }
  };

  return (
    <div className="flex items-center gap-1 group">
      <span className="truncate max-w-[110px]" title={column.name}>{column.name}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            className={`p-0.5 rounded ${
              hasFilter
                ? "text-indigo-600"
                : "text-slate-300 opacity-0 group-hover:opacity-100 hover:text-slate-600"
            }`}
            data-testid={`col-filter-${column.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            <Filter className="w-3 h-3" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="p-2 w-64" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-1">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
              Filter · {column.name}
            </div>
            {hasFilter && (
              <button
                onClick={clear}
                className="text-[11px] text-indigo-600 hover:text-indigo-700"
                data-testid={`col-filter-clear-${column.id}`}
              >
                Clear
              </button>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto space-y-0.5">
            {counts.length === 0 ? (
              <div className="text-xs text-slate-400 py-2 text-center">
                No values yet.
              </div>
            ) : (
              counts.map((c) => (
                <label
                  key={c.value}
                  className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-slate-50 cursor-pointer text-sm"
                >
                  <input
                    type="checkbox"
                    className="rounded accent-indigo-600"
                    checked={(activeValues || []).includes(c.value)}
                    onChange={() => toggle(c.value)}
                    data-testid={`col-filter-value-${column.id}-${c.value}`}
                  />
                  <span className="flex-1 text-slate-700 truncate">
                    {c.value === "__empty" ? (
                      <span className="italic text-slate-400">(empty)</span>
                    ) : (
                      c.value
                    )}
                  </span>
                  <span className="text-mono text-[10.5px] text-slate-400">
                    {c.count}
                  </span>
                </label>
              ))
            )}
          </div>
        </PopoverContent>
      </Popover>

      <Popover>
        <PopoverTrigger asChild>
          <button
            className="p-0.5 text-slate-300 opacity-0 group-hover:opacity-100 hover:text-slate-600 rounded"
            data-testid={`col-menu-${column.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            <MoreVertical className="w-3 h-3" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="p-1 w-40">
          <button
            onClick={() => setConfirmDel(true)}
            className="w-full text-left text-xs text-red-600 hover:bg-red-50 rounded px-2 py-1.5 flex items-center gap-1.5"
            data-testid={`col-delete-${column.id}`}
          >
            <Trash2 className="w-3 h-3" />
            Delete column
          </button>
        </PopoverContent>
      </Popover>

      <Dialog open={confirmDel} onOpenChange={setConfirmDel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete column &ldquo;{column.name}&rdquo;?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-slate-600">
            All cell values under this column will be erased for every contact in
            this campaign. This cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDel(false)}>
              Cancel
            </Button>
            <Button
              onClick={doDelete}
              className="bg-red-600 hover:bg-red-700 text-white"
              data-testid={`col-delete-confirm-${column.id}`}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Cell renderer for a person / column pair.
 * Renders inline editor based on column.kind.
 */
export function CustomCell({ campaignId, personId, column, value, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  const save = async (newValue) => {
    setSaving(true);
    try {
      await api.patch(`/campaigns/${campaignId}/cells/${personId}`, {
        column_id: column.id,
        value: newValue,
      });
      onSaved?.(newValue);
      setEditing(false);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (column.kind === "checkbox") {
    return (
      <input
        type="checkbox"
        className="rounded accent-indigo-600"
        checked={!!value}
        onChange={(e) => save(e.target.checked)}
        data-testid={`cell-${personId}-${column.id}`}
        onClick={(e) => e.stopPropagation()}
      />
    );
  }

  if (column.kind === "select") {
    return (
      <select
        value={value ?? ""}
        onChange={(e) => save(e.target.value || null)}
        onClick={(e) => e.stopPropagation()}
        className={`text-[12px] border border-transparent hover:border-slate-200 rounded px-1 py-0.5 focus:border-indigo-400 focus:bg-white outline-none w-full ${
          value ? "text-slate-700" : "text-slate-300"
        }`}
        data-testid={`cell-${personId}-${column.id}`}
      >
        <option value="">—</option>
        {(column.options || []).map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }

  // text
  return editing ? (
    <input
      type="text"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => save(draft)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          save(draft);
        } else if (e.key === "Escape") {
          setDraft(value ?? "");
          setEditing(false);
        }
      }}
      onClick={(e) => e.stopPropagation()}
      autoFocus
      disabled={saving}
      className="text-[12px] w-full border border-indigo-300 rounded px-1 py-0.5 outline-none"
      data-testid={`cell-${personId}-${column.id}-input`}
    />
  ) : (
    <button
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
      }}
      className={`w-full text-left text-[12px] truncate px-1 py-0.5 rounded hover:bg-slate-50 ${
        value ? "text-slate-700" : "text-slate-300 italic"
      }`}
      data-testid={`cell-${personId}-${column.id}`}
    >
      {value || "—"}
    </button>
  );
}
