import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Users, Building2, Send, GitMerge, Upload, Search, Sparkles } from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/stats/overview").then(({ data }) => setStats(data));
  }, []);

  return (
    <div className="h-full flex flex-col" data-testid="dashboard-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">Dashboard</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Overview of your unified contact database.
        </p>
      </div>

      <div className="flex-1 overflow-auto p-6 max-w-6xl w-full">
        <form
          className="mb-6"
          onSubmit={(e) => {
            e.preventDefault();
            if (search.trim())
              navigate(`/people?search=${encodeURIComponent(search.trim())}`);
          }}
        >
          <div className="relative max-w-2xl">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Global search — find anyone by name, email, company…"
              className="pl-9 h-11 text-[15px]"
              data-testid="global-search-input"
            />
          </div>
        </form>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            label="Unique people"
            value={stats?.total_people}
            icon={Users}
            onClick={() => navigate("/people")}
            testId="stat-people"
          />
          <StatCard
            label="Companies"
            value={stats?.total_companies}
            icon={Building2}
            onClick={() => navigate("/companies")}
            testId="stat-companies"
          />
          <StatCard
            label="Active campaigns"
            value={stats?.active_campaigns}
            icon={Send}
            onClick={() => navigate("/campaigns")}
            testId="stat-campaigns"
            hint={`${stats?.total_campaigns || 0} total`}
          />
          <StatCard
            label="Pending duplicates"
            value={stats?.pending_duplicates}
            icon={GitMerge}
            onClick={() => navigate("/duplicates")}
            testId="stat-duplicates"
            highlight={stats?.pending_duplicates > 0}
          />
        </div>

        <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-white border border-slate-200 rounded-md p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
                Recent imports
              </div>
              <button
                onClick={() => navigate("/import")}
                className="text-xs text-indigo-600 hover:text-indigo-700"
              >
                New import →
              </button>
            </div>
            {stats?.recent_batches?.length ? (
              <div className="divide-y divide-slate-100">
                {stats.recent_batches.map((b) => (
                  <div key={b.id} className="flex items-center justify-between py-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-900 truncate">
                        {b.file_name}
                      </div>
                      <div className="text-xs text-slate-500 truncate">
                        → {b.campaign_name || "—"} ·{" "}
                        {b.created_at && new Date(b.created_at).toLocaleString()}
                      </div>
                    </div>
                    <div className="text-xs text-slate-600 flex items-center gap-3 shrink-0">
                      <span>
                        <span className="text-mono font-medium text-emerald-700">
                          +{b.stats?.new_people || 0}
                        </span>{" "}
                        new
                      </span>
                      <span>
                        <span className="text-mono font-medium text-slate-700">
                          {b.stats?.matched_people || 0}
                        </span>{" "}
                        matched
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 italic py-4">
                No imports yet.
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-md p-5">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              <div className="text-sm font-semibold text-slate-900">Chat assistant</div>
            </div>
            <p className="text-xs text-slate-500">
              Ask questions like &ldquo;show me everyone from HDFC Bank&rdquo; or &ldquo;who&apos;s in Non-QM but not
              MBA Annual&rdquo;.
            </p>
            <div className="mt-3 space-y-1.5">
              <button
                onClick={() => navigate("/campaigns")}
                className="w-full text-left text-xs px-2.5 py-2 rounded bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-700"
              >
                → Compare campaign overlap
              </button>
              <button
                onClick={() => navigate("/duplicates")}
                className="w-full text-left text-xs px-2.5 py-2 rounded bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-700"
              >
                → Review possible duplicates
              </button>
              <button
                onClick={() => navigate("/import")}
                className="w-full text-left text-xs px-2.5 py-2 rounded bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-700"
              >
                → Import a new sheet
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, onClick, testId, hint, highlight }) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className={`text-left bg-white border rounded-md p-4 hover:shadow-sm hover:border-indigo-300 transition-all ${
        highlight ? "border-amber-200 bg-amber-50/40" : "border-slate-200"
      }`}
    >
      <div className="flex items-center justify-between">
        <div
          className={`w-8 h-8 rounded-md flex items-center justify-center ${
            highlight ? "bg-amber-100 text-amber-700" : "bg-indigo-50 text-indigo-600"
          }`}
        >
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-bold text-slate-900 text-mono">
        {value ?? "—"}
      </div>
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mt-0.5">
        {label}
      </div>
      {hint && <div className="text-[11px] text-slate-400 mt-0.5">{hint}</div>}
    </button>
  );
}
