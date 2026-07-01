import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { StickyNote, Loader2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Inline notes editor cell for tables.
 * Shows a preview; clicking opens a small popover with a textarea to edit.
 * Calls onSaved(newNotes) after a successful save so the parent can update its
 * local row without a full refetch.
 */
export default function NotesCell({
  entity, // "person" | "company"
  id,
  initialNotes,
  compact = true,
  onSaved,
  testId,
}) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState(initialNotes || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setNotes(initialNotes || "");
  }, [initialNotes]);

  const save = async () => {
    setSaving(true);
    try {
      const endpoint = entity === "company" ? `/companies/${id}` : `/people/${id}`;
      const { data } = await api.patch(endpoint, { notes });
      const newNotes = data?.notes ?? notes;
      onSaved?.(newNotes);
      toast.success("Notes saved");
      setOpen(false);
    } catch (_e) {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const preview = (initialNotes || "").trim();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          onClick={(e) => e.stopPropagation()}
          className={`w-full text-left text-slate-600 hover:text-indigo-700 transition-colors ${
            compact ? "text-[12.5px]" : "text-sm"
          }`}
        >
          {preview ? (
            <span className="line-clamp-2 leading-snug">{preview}</span>
          ) : (
            <span className="text-slate-300 italic inline-flex items-center gap-1">
              <StickyNote className="w-3 h-3" />
              Add note
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-80 p-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
          {entity === "company" ? "Company notes" : "Contact notes"}
        </div>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={5}
          placeholder="Update, next steps, warm intro details…"
          className="text-sm"
          data-testid={`${testId}-textarea`}
        />
        <div className="mt-2 flex justify-end gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setNotes(initialNotes || "");
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={save}
            disabled={saving || notes === (initialNotes || "")}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
            data-testid={`${testId}-save`}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Save"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
