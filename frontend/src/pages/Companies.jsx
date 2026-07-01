import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Search,
  Building2,
  Users as UsersIcon,
  GitMerge,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Trash2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function CompaniesPage() {
  const { user } = useAuth();
  const isPrivileged = user?.role === "admin" || user?.role === "owner";
  const [q, setQ] = useState("");
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 60;
  const navigate = useNavigate();
  const [mergeGroups, setMergeGroups] = useState([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [reviewGroup, setReviewGroup] = useState(null);
  const [keepId, setKeepId] = useState(null);
  const [merging, setMerging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const reload = () => {
    setLoading(true);
    api
      .get("/companies", { params: { q, page, page_size: pageSize } })
      .then(({ data }) => setData(data))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    api
      .get("/companies", { params: { q, page, page_size: pageSize } })
      .then(({ data }) => setData(data))
      .finally(() => setLoading(false));
  }, [q, page]);

  const loadCandidates = async () => {
    setLoadingCandidates(true);
    try {
      const { data } = await api.get("/companies/merge-candidates");
      setMergeGroups(data.groups || []);
    } catch (e) {
      // Non-blocking — the merge-candidates band is optional UX.
      console.error("Failed to load merge candidates", e);
    } finally {
      setLoadingCandidates(false);
    }
  };

  useEffect(() => {
    loadCandidates();
  }, []);

  const openReview = (group) => {
    setReviewGroup(group);
    // Default: keep the company with the most people
    const best = [...group.companies].sort(
      (a, b) => (b.people_count || 0) - (a.people_count || 0)
    )[0];
    setKeepId(best?.id || group.companies[0]?.id || null);
  };

  const executeMerge = async () => {
    if (!reviewGroup || !keepId) return;
    setMerging(true);
    try {
      const others = reviewGroup.companies.filter((c) => c.id !== keepId).map((c) => c.id);
      const { data } = await api.post("/companies/merge", {
        keep_company_id: keepId,
        merge_company_ids: others,
      });
      toast.success(
        `Merged ${others.length} companies · ${data.moved || 0} people re-assigned`
      );
      setReviewGroup(null);
      setKeepId(null);
      // Refresh
      const [{ data: list }, _] = await Promise.all([
        api.get("/companies", { params: { q, page, page_size: pageSize } }),
        loadCandidates(),
      ]);
      setData(list);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Merge failed");
    } finally {
      setMerging(false);
    }
  };

  const deleteCompany = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const { data: res } = await api.delete(`/companies/${deleteTarget.id}`);
      toast.success(
        `Deleted "${deleteTarget.name}"` +
          (res.people_unlinked
            ? ` · ${res.people_unlinked} contact${res.people_unlinked === 1 ? "" : "s"} unlinked`
            : "")
      );
      setDeleteTarget(null);
      reload();
      loadCandidates();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / pageSize));

  return (
    <div className="h-full flex flex-col" data-testid="companies-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">Companies</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {data.total.toLocaleString()} organizations
              {mergeGroups.length > 0 && (
                <span className="ml-2 text-amber-700">
                  · {mergeGroups.length} possible duplicate{mergeGroups.length > 1 ? "s" : ""}
                </span>
              )}
            </p>
          </div>
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
              placeholder="Search company…"
              data-testid="companies-search-input"
              className="pl-9 h-9"
            />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* Merge candidates */}
        {mergeGroups.length > 0 && (
          <div className="mb-6" data-testid="merge-candidates-section">
            <div className="flex items-center gap-2 mb-2">
              <AlertCircle className="w-4 h-4 text-amber-600" />
              <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
                Possible duplicate companies ({mergeGroups.length})
              </div>
            </div>
            <div className="space-y-2">
              {mergeGroups.map((g, i) => {
                const groupKey = g.companies.map((c) => c.id).sort().join("|");
                return (
                <div
                  key={groupKey}
                  data-testid={`merge-group-${i}`}
                  className="bg-amber-50 border border-amber-200 rounded-md p-3 flex items-center justify-between gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-slate-500 mb-1">
                      Likely the same organization:
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {g.companies.map((c) => (
                        <div
                          key={c.id}
                          className="bg-white border border-slate-200 rounded px-2 py-0.5 text-sm text-slate-800 flex items-center gap-1.5"
                        >
                          <Building2 className="w-3 h-3 text-slate-400" />
                          <span>{c.name}</span>
                          <span className="text-mono text-[10.5px] text-slate-400">
                            {c.people_count}p
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    onClick={() => openReview(g)}
                    data-testid={`review-merge-${i}`}
                  >
                    <GitMerge className="w-3.5 h-3.5 mr-1.5" />
                    Review
                  </Button>
                </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Companies grid */}
        {loading ? (
          <div className="text-slate-400 text-sm flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : data.items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            No companies yet — import a sheet to get started.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {data.items.map((c) => (
                <div
                  key={c.id}
                  data-testid={`company-card-${c.id}`}
                  className="group relative text-left bg-white border border-slate-200 rounded-md p-4 hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() =>
                    navigate(`/people?company=${encodeURIComponent(c.name)}`)
                  }
                >
                  {isPrivileged && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget(c);
                      }}
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-50 text-slate-300 hover:text-red-600"
                      data-testid={`delete-company-${c.id}`}
                      title="Delete company"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-md bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                      <Building2 className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-slate-900 truncate">
                        {c.name}
                      </div>
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
                      {c.notes && (
                        <div className="mt-2 text-[11.5px] text-slate-500 line-clamp-2">
                          {c.notes}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-between text-xs text-slate-500">
                <div>
                  Showing{" "}
                  <span className="text-mono text-slate-700">
                    {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data.total)}
                  </span>{" "}
                  of{" "}
                  <span className="text-mono text-slate-700">
                    {data.total.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-mono">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Merge review dialog */}
      <Dialog
        open={!!reviewGroup}
        onOpenChange={(o) => {
          if (!o) {
            setReviewGroup(null);
            setKeepId(null);
          }
        }}
      >
        <DialogContent data-testid="merge-review-dialog">
          <DialogHeader>
            <DialogTitle>Merge duplicate companies</DialogTitle>
          </DialogHeader>
          {reviewGroup && (
            <div>
              <p className="text-sm text-slate-600">
                Pick the record to keep. The others will be deleted, and all their people
                will be re-assigned to the kept company.
              </p>
              <div className="mt-4 space-y-2">
                {reviewGroup.companies.map((c) => (
                  <label
                    key={c.id}
                    className={`flex items-center gap-3 border rounded-md p-3 cursor-pointer ${
                      keepId === c.id
                        ? "border-indigo-500 bg-indigo-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                    data-testid={`merge-option-${c.id}`}
                  >
                    <input
                      type="radio"
                      className="accent-indigo-600"
                      checked={keepId === c.id}
                      onChange={() => setKeepId(c.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-900 truncate">
                        {c.name}
                      </div>
                      {c.email_domain && (
                        <div className="text-mono text-[11.5px] text-slate-500 truncate">
                          @{c.email_domain}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">
                      <span className="text-mono font-medium text-slate-900">
                        {c.people_count}
                      </span>{" "}
                      people
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setReviewGroup(null);
                setKeepId(null);
              }}
              disabled={merging}
            >
              Cancel
            </Button>
            <Button
              onClick={executeMerge}
              disabled={merging || !keepId}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="execute-merge-btn"
            >
              {merging ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <GitMerge className="w-3.5 h-3.5 mr-1.5" />
                  Merge
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete company confirm dialog */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent data-testid="delete-company-dialog">
          <DialogHeader>
            <DialogTitle>Delete &ldquo;{deleteTarget?.name}&rdquo;?</DialogTitle>
            <DialogDescription>
              {deleteTarget?.people_count > 0 ? (
                <>
                  This company has{" "}
                  <span className="font-medium text-slate-800">
                    {deleteTarget.people_count} contact
                    {deleteTarget.people_count === 1 ? "" : "s"}
                  </span>{" "}
                  linked to it. Deleting the company will unlink them (the
                  contacts themselves stay in your directory but their company
                  will be blank). You can re-assign them later.
                </>
              ) : (
                <>
                  This company has no contacts linked. Delete safely — the
                  company record will be permanently removed.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              onClick={deleteCompany}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700 text-white"
              data-testid="confirm-delete-company"
            >
              {deleting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Delete
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
