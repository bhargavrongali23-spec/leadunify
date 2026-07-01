import { useMemo, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { openPerson } from "@/components/AppLayout";
import { CampaignChip } from "@/components/CampaignChip";
import NotesCell from "@/components/NotesCell";
import {
  AddColumnButton,
  CustomColumnHeader,
  CustomCell,
} from "@/components/CustomColumns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Search,
  Linkedin,
  Filter,
  Download,
  ChevronLeft,
  ChevronRight,
  X,
  Users as UsersIcon,
  Loader2,
  Save,
  Upload,
  Trash2,
  Flag,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

export default function PeoplePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [debounced, setDebounced] = useState(searchParams.get("search") || "");
  const [campaigns, setCampaigns] = useState([]);
  const [inCampaigns, setInCampaigns] = useState(
    searchParams.get("in") ? [searchParams.get("in")] : []
  );
  const [notInCampaigns, setNotInCampaigns] = useState(
    searchParams.get("notIn") ? [searchParams.get("notIn")] : []
  );
  const [companyFilter, setCompanyFilter] = useState(searchParams.get("company") || "");
  const [needsEnrichment, setNeedsEnrichment] = useState(
    searchParams.get("needs_enrichment") === "1"
  );
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [savedFilters, setSavedFilters] = useState([]);
  const [saveName, setSaveName] = useState("");
  const [activeCampaignInfo, setActiveCampaignInfo] = useState(null);
  const [activeCompanyInfo, setActiveCompanyInfo] = useState(null);
  const [activeCompany, setActiveCompany] = useState(null); // full company doc (for notes editor)
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [customColumns, setCustomColumns] = useState([]);
  const [customFilters, setCustomFilters] = useState({}); // { column_id: [values] }
  const [valueCounts, setValueCounts] = useState({}); // { column_id: [{value, count}] }

  // Re-sync when the URL changes (e.g., user clicks a different campaign card).
  useEffect(() => {
    const s = searchParams.get("search") || "";
    const inC = searchParams.get("in");
    const notInC = searchParams.get("notIn");
    const co = searchParams.get("company") || "";
    setSearch(s);
    setDebounced(s);
    setInCampaigns(inC ? [inC] : []);
    setNotInCampaigns(notInC ? [notInC] : []);
    setCompanyFilter(co);
    setPage(1);
  }, [searchParams.toString()]);

  // Compute the "context" label shown in the header (campaign name or company name)
  useEffect(() => {
    if (inCampaigns.length === 1 && campaigns.length) {
      const c = campaigns.find((x) => x.id === inCampaigns[0]);
      setActiveCampaignInfo(c || null);
    } else {
      setActiveCampaignInfo(null);
    }
  }, [inCampaigns, campaigns]);

  useEffect(() => {
    setActiveCompanyInfo(companyFilter || null);
  }, [companyFilter]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/campaigns");
        setCampaigns(data.items || []);
      } catch (_e) {
        /* ignore */
      }
    })();
    (async () => {
      try {
        const { data } = await api.get("/saved-filters");
        setSavedFilters(data.items || []);
      } catch (_e) {
        /* ignore */
      }
    })();
  }, []);

  const filters = useMemo(
    () => ({
      search: debounced || null,
      company_name: companyFilter || null,
      in_campaigns: inCampaigns.length ? inCampaigns : null,
      not_in_campaigns: notInCampaigns.length ? notInCampaigns : null,
      needs_enrichment: needsEnrichment || null,
      custom_filters: Object.keys(customFilters).length ? customFilters : null,
      page,
      page_size: pageSize,
    }),
    [debounced, companyFilter, inCampaigns, notInCampaigns, needsEnrichment, customFilters, page]
  );

  // Load custom columns & value counts when exactly one campaign filter is active
  const singleCampaignId = inCampaigns.length === 1 ? inCampaigns[0] : null;

  const loadCustomColumns = async (cid) => {
    if (!cid) {
      setCustomColumns([]);
      setValueCounts({});
      setCustomFilters({});
      return;
    }
    try {
      const [{ data: cols }, { data: counts }] = await Promise.all([
        api.get(`/campaigns/${cid}/columns`),
        api.get(`/campaigns/${cid}/cell-value-counts`),
      ]);
      setCustomColumns(cols.items || []);
      setValueCounts(counts.counts || {});
    } catch (_e) {
      setCustomColumns([]);
      setValueCounts({});
    }
  };

  useEffect(() => {
    loadCustomColumns(singleCampaignId);
  }, [singleCampaignId]);

  const refreshValueCounts = async () => {
    if (!singleCampaignId) return;
    try {
      const { data } = await api.get(`/campaigns/${singleCampaignId}/cell-value-counts`);
      setValueCounts(data.counts || {});
    } catch (_e) { /* ignore */ }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .post("/people/query", filters)
      .then(({ data }) => {
        if (!cancelled) setData(data);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / pageSize));

  // Load full company doc (with notes) when navigating with ?company=<name>
  useEffect(() => {
    if (!companyFilter) {
      setActiveCompany(null);
      return;
    }
    let cancelled = false;
    api
      .get("/companies/lookup/by-name", { params: { name: companyFilter } })
      .then(({ data }) => {
        if (!cancelled) setActiveCompany(data.company || null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [companyFilter]);

  // Clear selection when filters change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [debounced, companyFilter, inCampaigns.join(","), notInCampaigns.join(","), page]);

  const exportCsv = async (format) => {
    try {
      const hasSelection = selectedIds.size > 0;
      const url = hasSelection
        ? `/people/export?format=${format}&ids=${Array.from(selectedIds).join(",")}`
        : `/people/export?format=${format}`;
      const response = await api.post(url, filters, { responseType: "blob" });
      const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = format === "xlsx" ? "people_export.xlsx" : "people_export.csv";
      a.click();
      window.URL.revokeObjectURL(blobUrl);
      toast.success(
        hasSelection
          ? `Exported ${selectedIds.size} selected`
          : "Export downloaded"
      );
    } catch (_e) {
      toast.error("Export failed");
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allVisibleSelected =
    data.items.length > 0 && data.items.every((p) => selectedIds.has(p.id));

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        data.items.forEach((p) => next.delete(p.id));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        data.items.forEach((p) => next.add(p.id));
        return next;
      });
    }
  };

  const updateRowNotes = (personId, newNotes) => {
    setData((d) => ({
      ...d,
      items: d.items.map((p) => (p.id === personId ? { ...p, notes: newNotes } : p)),
    }));
  };

  const [confirmDelete, setConfirmDelete] = useState(null);

  const runBulkDelete = async (mode) => {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    try {
      if (mode === "all") {
        const { data } = await api.post("/people/bulk-delete", { ids });
        toast.success(`Deleted ${data.deleted} contact${data.deleted === 1 ? "" : "s"}`);
      } else if (mode === "campaign" && activeCampaignInfo) {
        const { data } = await api.post("/people/bulk-remove-from-campaign", {
          ids,
          campaign_id: activeCampaignInfo.id,
        });
        toast.success(
          `Removed ${data.removed} contact${data.removed === 1 ? "" : "s"} from ${activeCampaignInfo.name}`
        );
      }
      setSelectedIds(new Set());
      setConfirmDelete(null);
      // Refresh
      const { data: refreshed } = await api.post("/people/query", filters);
      setData(refreshed);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  const activeFilterCount =
    (inCampaigns.length ? 1 : 0) +
    (notInCampaigns.length ? 1 : 0) +
    (companyFilter ? 1 : 0);

  const clearFilters = () => {
    setInCampaigns([]);
    setNotInCampaigns([]);
    setCompanyFilter("");
    setSearch("");
    setPage(1);
    setSearchParams({});
  };

  const saveCurrent = async () => {
    if (!saveName.trim()) {
      toast.error("Give your filter a name");
      return;
    }
    try {
      const { data } = await api.post("/saved-filters", {
        name: saveName.trim(),
        filters: {
          search: debounced,
          company_name: companyFilter,
          in_campaigns: inCampaigns,
          not_in_campaigns: notInCampaigns,
        },
      });
      setSavedFilters((prev) => [data, ...prev]);
      setSaveName("");
      toast.success("Saved");
    } catch (_) {
      toast.error("Could not save");
    }
  };

  const applySaved = (f) => {
    setSearch(f.filters?.search || "");
    setCompanyFilter(f.filters?.company_name || "");
    setInCampaigns(f.filters?.in_campaigns || []);
    setNotInCampaigns(f.filters?.not_in_campaigns || []);
    setPage(1);
  };

  const deleteSaved = async (id) => {
    await api.delete(`/saved-filters/${id}`);
    setSavedFilters((prev) => prev.filter((s) => s.id !== id));
  };

  return (
    <div className="h-full flex flex-col" data-testid="people-page">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              {activeCampaignInfo ? (
                <span data-testid="context-campaign-title">
                  Campaign · <span className="text-indigo-700">{activeCampaignInfo.name}</span>
                </span>
              ) : activeCompanyInfo ? (
                <span data-testid="context-company-title">
                  Company · <span className="text-indigo-700">{activeCompanyInfo}</span>
                </span>
              ) : (
                "People Directory"
              )}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {loading
                ? "Loading…"
                : activeCampaignInfo
                ? `${data.total.toLocaleString()} people in this campaign`
                : activeCompanyInfo
                ? `${data.total.toLocaleString()} people at ${activeCompanyInfo}`
                : `${data.total.toLocaleString()} unique people`}
              {(activeCampaignInfo || activeCompanyInfo) && (
                <button
                  onClick={clearFilters}
                  data-testid="clear-context-filter"
                  className="ml-2 text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  · Show all people
                </button>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {singleCampaignId && (
              <AddColumnButton
                campaignId={singleCampaignId}
                onAdded={() => loadCustomColumns(singleCampaignId)}
              />
            )}
            {selectedIds.size > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    data-testid="bulk-delete-btn"
                    className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800"
                  >
                    <Trash2 className="w-4 h-4 mr-1.5" />
                    Delete ({selectedIds.size})
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  {activeCampaignInfo && (
                    <DropdownMenuItem
                      data-testid="delete-from-campaign-only"
                      onClick={() => setConfirmDelete("campaign")}
                    >
                      <div>
                        <div className="text-sm font-medium">
                          Remove from this campaign only
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          Contact + other campaigns stay intact
                        </div>
                      </div>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem
                    data-testid="delete-from-everywhere"
                    onClick={() => setConfirmDelete("all")}
                  >
                    <div>
                      <div className="text-sm font-medium text-red-700">
                        Delete from all lists & campaigns
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Removes the contact record entirely
                      </div>
                    </div>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant={selectedIds.size > 0 ? "default" : "outline"}
                  size="sm"
                  data-testid="export-btn"
                  className={selectedIds.size > 0 ? "bg-indigo-600 hover:bg-indigo-700 text-white" : ""}
                >
                  <Download className="w-4 h-4 mr-1.5" />
                  {selectedIds.size > 0
                    ? `Export ${selectedIds.size} selected`
                    : "Export"}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem data-testid="export-csv" onClick={() => exportCsv("csv")}>
                  Export as CSV
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="export-xlsx" onClick={() => exportCsv("xlsx")}>
                  Export as XLSX
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              size="sm"
              data-testid="goto-import-btn"
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={() => navigate("/import")}
            >
              <Upload className="w-4 h-4 mr-1.5" />
              Import
            </Button>
          </div>
        </div>

        {/* Filter row */}
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[280px] max-w-xl">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search name, email, company, title…"
              data-testid="search-input"
              className="pl-9 text-mono h-9"
            />
          </div>

          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" data-testid="filter-in-campaign-btn">
                <Filter className="w-4 h-4 mr-1.5" />
                In campaign
                {inCampaigns.length > 0 && (
                  <span className="ml-1.5 chip chip-active !py-0 !px-1.5 !text-[10px]">
                    {inCampaigns.length}
                  </span>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="p-2 w-72">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide px-2 py-1">
                Person is in ANY of
              </div>
              <div className="max-h-64 overflow-y-auto">
                {campaigns.map((c) => (
                  <label
                    key={c.id}
                    className="flex items-center gap-2 px-2 py-1.5 hover:bg-slate-50 rounded cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      data-testid={`filter-in-${c.id}`}
                      className="rounded accent-indigo-600"
                      checked={inCampaigns.includes(c.id)}
                      onChange={(e) => {
                        setPage(1);
                        setInCampaigns((prev) =>
                          e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)
                        );
                      }}
                    />
                    <span className="flex-1 truncate">{c.name}</span>
                    <span className="text-[10px] text-slate-400 text-mono">
                      {c.people_count || 0}
                    </span>
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" data-testid="filter-not-in-campaign-btn">
                <X className="w-4 h-4 mr-1.5 text-amber-500" />
                Not in campaign
                {notInCampaigns.length > 0 && (
                  <span className="ml-1.5 chip chip-duplicate !py-0 !px-1.5 !text-[10px]">
                    {notInCampaigns.length}
                  </span>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="p-2 w-72">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide px-2 py-1">
                Person is NOT in
              </div>
              <div className="max-h-64 overflow-y-auto">
                {campaigns.map((c) => (
                  <label
                    key={c.id}
                    className="flex items-center gap-2 px-2 py-1.5 hover:bg-slate-50 rounded cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      data-testid={`filter-notin-${c.id}`}
                      className="rounded accent-amber-500"
                      checked={notInCampaigns.includes(c.id)}
                      onChange={(e) => {
                        setPage(1);
                        setNotInCampaigns((prev) =>
                          e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)
                        );
                      }}
                    />
                    <span className="flex-1 truncate">{c.name}</span>
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          <Input
            placeholder="Company contains…"
            value={companyFilter}
            data-testid="filter-company-input"
            onChange={(e) => {
              setCompanyFilter(e.target.value);
              setPage(1);
            }}
            className="h-9 max-w-[180px]"
          />

          <Button
            variant={needsEnrichment ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setNeedsEnrichment((v) => !v);
              setPage(1);
            }}
            data-testid="filter-needs-enrichment"
            className={needsEnrichment ? "bg-amber-500 hover:bg-amber-600 text-white border-amber-500" : ""}
          >
            <Flag className="w-3.5 h-3.5 mr-1.5" />
            Needs enrichment
          </Button>

          {activeFilterCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              data-testid="clear-filters-btn"
              className="text-slate-500"
            >
              Clear filters
            </Button>
          )}

          <div className="flex-1" />

          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" data-testid="saved-filters-btn">
                <Save className="w-4 h-4 mr-1.5" />
                Saved
                {savedFilters.length > 0 && (
                  <span className="ml-1.5 text-[10px] text-slate-500 text-mono">
                    {savedFilters.length}
                  </span>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="p-3 w-80">
              <div className="flex gap-2 mb-3">
                <Input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="Name this filter"
                  className="h-8 text-sm"
                  data-testid="save-filter-name-input"
                />
                <Button
                  size="sm"
                  onClick={saveCurrent}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white h-8"
                  data-testid="save-filter-btn"
                >
                  Save
                </Button>
              </div>
              <div className="max-h-64 overflow-y-auto -mx-1">
                {savedFilters.length === 0 ? (
                  <div className="text-xs text-slate-400 px-1 py-2">
                    Save the current filter combination to reuse later.
                  </div>
                ) : (
                  savedFilters.map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center gap-2 px-2 py-1.5 hover:bg-slate-50 rounded text-sm"
                    >
                      <button
                        type="button"
                        className="flex-1 text-left truncate text-slate-700 hover:text-indigo-700"
                        onClick={() => applySaved(s)}
                        data-testid={`apply-saved-${s.id}`}
                      >
                        {s.name}
                      </button>
                      <button
                        type="button"
                        className="text-slate-300 hover:text-red-500"
                        onClick={() => deleteSaved(s.id)}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* Company context banner (with editable notes) */}
      {activeCompany && (
        <div className="border-b border-slate-200 bg-indigo-50/40 px-6 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                Company overview
              </div>
              <div className="text-lg font-semibold text-slate-900 mt-0.5">
                {activeCompany.name}
              </div>
              {activeCompany.email_domain && (
                <div className="text-mono text-[12px] text-slate-500">
                  @{activeCompany.email_domain}
                </div>
              )}
            </div>
            <div className="w-full sm:w-96 shrink-0">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
                Company notes
              </div>
              <div className="bg-white border border-slate-200 rounded-md p-2 min-h-[40px]">
                <NotesCell
                  entity="company"
                  id={activeCompany.id}
                  initialNotes={activeCompany.notes}
                  compact={false}
                  testId="company-notes"
                  onSaved={(newNotes) =>
                    setActiveCompany((c) => (c ? { ...c, notes: newNotes } : c))
                  }
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading && data.items.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading people…
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState onImport={() => navigate("/import")} />
        ) : (
          <table className="w-full text-sm" data-testid="people-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 sticky top-0 z-10">
              <tr>
                <th className="px-4 py-2.5 w-8">
                  <input
                    type="checkbox"
                    className="rounded accent-indigo-600 cursor-pointer"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    data-testid="select-all-checkbox"
                  />
                </th>
                <th className="px-3 py-2.5 text-left font-semibold">Name</th>
                <th className="px-3 py-2.5 text-left font-semibold">Company</th>
                <th className="px-3 py-2.5 text-left font-semibold">Title</th>
                <th className="px-3 py-2.5 text-left font-semibold">Email</th>
                <th className="px-3 py-2.5 text-left font-semibold">Phone</th>
                <th className="px-3 py-2.5 text-left font-semibold w-8">LI</th>
                <th className="px-3 py-2.5 text-left font-semibold">Campaigns</th>
                <th className="px-3 py-2.5 text-left font-semibold w-[220px]">Notes</th>
                {customColumns.map((col) => (
                  <th
                    key={col.id}
                    className="px-3 py-2.5 text-left font-semibold whitespace-nowrap"
                    data-testid={`col-header-${col.id}`}
                  >
                    <CustomColumnHeader
                      campaignId={singleCampaignId}
                      column={col}
                      valueCounts={valueCounts[col.id] || []}
                      activeValues={customFilters[col.id] || []}
                      onFilterChange={(vals) => {
                        setCustomFilters((prev) => {
                          const next = { ...prev };
                          if (!vals || vals.length === 0) delete next[col.id];
                          else next[col.id] = vals;
                          return next;
                        });
                        setPage(1);
                      }}
                      onDeleted={() => loadCustomColumns(singleCampaignId)}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((p) => (
                <PersonRow
                  key={p.id}
                  person={p}
                  selected={selectedIds.has(p.id)}
                  onToggleSelect={() => toggleSelect(p.id)}
                  onNotesSaved={(n) => updateRowNotes(p.id, n)}
                  customColumns={customColumns}
                  singleCampaignId={singleCampaignId}
                  onCustomSaved={refreshValueCounts}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {data.total > 0 && (
        <div className="border-t border-slate-200 bg-white px-4 py-2.5 flex items-center justify-between text-xs text-slate-500">
          <div>
            Showing{" "}
            <span className="text-mono text-slate-700">
              {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data.total)}
            </span>{" "}
            of <span className="text-mono text-slate-700">{data.total.toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              data-testid="prev-page-btn"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <div className="text-mono text-slate-600">
              {page} / {totalPages}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              data-testid="next-page-btn"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Bulk delete confirmation */}
      <Dialog open={!!confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <DialogContent data-testid="confirm-delete-dialog">
          <DialogHeader>
            <DialogTitle>
              {confirmDelete === "all"
                ? `Delete ${selectedIds.size} contact${selectedIds.size === 1 ? "" : "s"}?`
                : `Remove ${selectedIds.size} contact${selectedIds.size === 1 ? "" : "s"} from ${activeCampaignInfo?.name}?`}
            </DialogTitle>
            <DialogDescription>
              {confirmDelete === "all" ? (
                <>
                  These contacts will be permanently removed from every campaign, every
                  list, and the People directory. This cannot be undone.
                </>
              ) : (
                <>
                  The contacts stay in your directory and in any other campaigns they
                  belong to — they&apos;ll just be removed from{" "}
                  <span className="font-medium">{activeCampaignInfo?.name}</span>.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => runBulkDelete(confirmDelete)}
              className={
                confirmDelete === "all"
                  ? "bg-red-600 hover:bg-red-700 text-white"
                  : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }
              data-testid="confirm-delete-btn"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              {confirmDelete === "all" ? "Delete permanently" : "Remove from campaign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PersonRow({ person, selected, onToggleSelect, onNotesSaved, customColumns = [], singleCampaignId, onCustomSaved }) {
  const [customValues, setCustomValues] = useState(person.custom_values || {});
  useEffect(() => {
    setCustomValues(person.custom_values || {});
  }, [person.custom_values, person.id]);
  return (
    <tr
      className={`row-hover cursor-pointer ${selected ? "bg-indigo-50/40" : ""}`}
      data-testid={`person-row-${person.id}`}
      onClick={() => openPerson(person.id)}
    >
      <td className="px-4 py-2.5 w-8" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="rounded accent-indigo-600 cursor-pointer"
          checked={!!selected}
          onChange={onToggleSelect}
          data-testid={`select-person-${person.id}`}
        />
      </td>
      <td className="px-3 py-2.5 min-w-[180px]">
        <div className="font-medium text-slate-900 truncate max-w-[220px]">{person.full_name}</div>
      </td>
      <td className="px-3 py-2.5 text-slate-700 truncate max-w-[160px]">
        {person.company_name || <span className="text-slate-300">—</span>}
      </td>
      <td className="px-3 py-2.5 text-slate-500 truncate max-w-[180px]">
        {person.job_title || <span className="text-slate-300">—</span>}
      </td>
      <td className="px-3 py-2.5 text-mono text-[12.5px] text-slate-600 truncate max-w-[220px]">
        {person.primary_email}
      </td>
      <td className="px-3 py-2.5 text-mono text-[12px] text-slate-600 whitespace-nowrap">
        {(person.phones || [])[0] || <span className="text-slate-300">—</span>}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1.5">
          {person.linkedin_url ? (
            <a
              href={person.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              data-testid={`linkedin-link-${person.id}`}
              className="text-slate-400 hover:text-indigo-600"
            >
              <Linkedin className="w-4 h-4" />
            </a>
          ) : (
            <span className="text-slate-200">
              <Linkedin className="w-4 h-4" />
            </span>
          )}
          {person.enrichment_flag && (
            <span
              data-testid={`enrichment-flag-${person.id}`}
              className="text-amber-500"
              title="Flagged for enrichment"
            >
              <Flag className="w-3.5 h-3.5" />
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-1 max-w-[280px]">
          {(person.campaigns || []).slice(0, 2).map((c) => (
            <CampaignChip
              key={c.id}
              name={c.name}
              status={c.status}
              testId={`chip-${person.id}-${c.id}`}
              onClick={(e) => {
                e.stopPropagation();
              }}
            />
          ))}
          {(person.campaigns || []).length > 2 && (
            <Popover>
              <PopoverTrigger asChild>
                <button
                  onClick={(e) => e.stopPropagation()}
                  className="chip chip-completed"
                  data-testid={`more-chips-${person.id}`}
                >
                  +{person.campaigns.length - 2} more
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="p-2 w-64">
                <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide px-1 py-1">
                  All campaigns
                </div>
                <div className="space-y-1">
                  {person.campaigns.map((c) => (
                    <div key={c.id} className="flex items-center">
                      <CampaignChip name={c.name} status={c.status} />
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          )}
        </div>
      </td>
      <td className="px-3 py-2.5 max-w-[220px] align-top" onClick={(e) => e.stopPropagation()}>
        <NotesCell
          entity="person"
          id={person.id}
          initialNotes={person.notes}
          onSaved={onNotesSaved}
          testId={`notes-${person.id}`}
        />
      </td>
      {customColumns.map((col) => (
        <td
          key={col.id}
          className="px-3 py-2.5 align-top whitespace-nowrap"
          onClick={(e) => e.stopPropagation()}
          data-testid={`cell-td-${person.id}-${col.id}`}
        >
          <CustomCell
            campaignId={singleCampaignId}
            personId={person.id}
            column={col}
            value={customValues[col.id]}
            onSaved={(newVal) => {
              setCustomValues((prev) => {
                const next = { ...prev };
                if (newVal === null || newVal === "" || newVal === undefined) {
                  delete next[col.id];
                } else {
                  next[col.id] = newVal;
                }
                return next;
              });
              onCustomSaved?.();
            }}
          />
        </td>
      ))}
    </tr>
  );
}

function EmptyState({ onImport }) {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <div className="w-14 h-14 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto">
          <UsersIcon className="w-6 h-6" strokeWidth={2} />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-900">No people match your filters</h2>
        <p className="mt-1 text-sm text-slate-500">
          Try clearing filters, or import a new sheet to grow the directory.
        </p>
        <Button
          onClick={onImport}
          className="mt-4 bg-indigo-600 hover:bg-indigo-700 text-white"
          data-testid="empty-import-btn"
        >
          <Upload className="w-4 h-4 mr-1.5" />
          Import a sheet
        </Button>
      </div>
    </div>
  );
}
