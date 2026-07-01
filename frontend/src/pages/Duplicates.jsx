import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { GitMerge, AlertCircle, CheckCircle2, X, Loader2, Users } from "lucide-react";
import { toast } from "sonner";
import { openPerson } from "@/components/AppLayout";

export default function DuplicatesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/duplicates");
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const act = async (id, action) => {
    setActionId(id);
    try {
      await api.post(`/duplicates/${id}/action`, { action });
      toast.success(action === "merge" ? "Merged" : "Dismissed");
      setItems((it) => it.filter((i) => i.id !== id));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Action failed");
    } finally {
      setActionId(null);
    }
  };

  return (
    <div className="h-full flex flex-col" data-testid="duplicates-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">Duplicate review</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Rows that matched an existing person by name + company, but had no hard identifier.
        </p>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16">
            <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
            <div className="mt-3 text-sm font-medium text-slate-900">
              Nothing to review — great job.
            </div>
            <div className="text-xs text-slate-500 mt-1">
              We&apos;ll flag ambiguous matches from future imports here.
            </div>
          </div>
        ) : (
          <div className="space-y-3 max-w-4xl mx-auto">
            {items.map((flag) => (
              <div
                key={flag.id}
                className="bg-white border border-slate-200 rounded-md overflow-hidden"
                data-testid={`dup-flag-${flag.id}`}
              >
                <div className="px-4 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2 text-xs text-amber-800">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Possible duplicate — {flag.match_reason} · from{" "}
                  <span className="text-mono">{flag.source_name || "—"}</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 divide-x divide-slate-100">
                  <PersonPreview
                    label="Existing"
                    person={flag.existing_person}
                    onOpen={() =>
                      flag.existing_person && openPerson(flag.existing_person.id)
                    }
                  />
                  <PersonPreview
                    label="Incoming"
                    person={flag.candidate_person}
                    onOpen={() =>
                      flag.candidate_person && openPerson(flag.candidate_person.id)
                    }
                  />
                </div>

                <div className="px-4 py-2.5 border-t border-slate-100 flex items-center justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => act(flag.id, "dismiss")}
                    disabled={actionId === flag.id}
                    data-testid={`dismiss-${flag.id}`}
                  >
                    <X className="w-3.5 h-3.5 mr-1" /> Not a duplicate
                  </Button>
                  <Button
                    size="sm"
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    onClick={() => act(flag.id, "merge")}
                    disabled={actionId === flag.id}
                    data-testid={`merge-${flag.id}`}
                  >
                    {actionId === flag.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                    ) : (
                      <GitMerge className="w-3.5 h-3.5 mr-1" />
                    )}
                    Merge into existing
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PersonPreview({ label, person, onOpen }) {
  if (!person) {
    return (
      <div className="p-4 text-xs text-slate-400 italic">No {label.toLowerCase()} record.</div>
    );
  }
  return (
    <button className="text-left p-4 hover:bg-slate-50 transition-colors" onClick={onOpen}>
      <div className="text-[10.5px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
        {label}
      </div>
      <div className="font-semibold text-slate-900">{person.full_name}</div>
      <div className="text-mono text-[11.5px] text-slate-500">{person.primary_email || "—"}</div>
      <div className="text-xs text-slate-500 mt-1">
        {person.company_name || "—"} · {person.job_title || "—"}
      </div>
      {person.linkedin_url && (
        <div className="text-mono text-[11px] text-slate-400 truncate mt-0.5">
          {person.linkedin_url}
        </div>
      )}
    </button>
  );
}
