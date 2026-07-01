import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Building2, Users as UsersIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function CompaniesPage() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    api
      .get("/companies", { params: { q } })
      .then(({ data }) => setItems(data.items || []))
      .finally(() => setLoading(false));
  }, [q]);

  return (
    <div className="h-full flex flex-col" data-testid="companies-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">Companies</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {items.length.toLocaleString()} organizations
            </p>
          </div>
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search company…"
              data-testid="companies-search-input"
              className="pl-9 h-9"
            />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            No companies yet — import a sheet to get started.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {items.map((c) => (
              <button
                key={c.id}
                data-testid={`company-card-${c.id}`}
                onClick={() =>
                  navigate(`/people?company=${encodeURIComponent(c.name)}`)
                }
                className="text-left bg-white border border-slate-200 rounded-md p-4 hover:border-indigo-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-md bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                    <Building2 className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-900 truncate">{c.name}</div>
                    {c.email_domain && (
                      <div className="text-mono text-[11.5px] text-slate-500 truncate">
                        @{c.email_domain}
                      </div>
                    )}
                    <div className="mt-2 inline-flex items-center gap-1 text-xs text-slate-600">
                      <UsersIcon className="w-3 h-3 text-slate-400" />
                      <span className="text-mono">{c.people_count || 0}</span>
                      <span className="text-slate-400">people</span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
