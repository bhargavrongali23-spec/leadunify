import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { UploadCloud, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2, X, Link2 } from "lucide-react";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";

const STANDARD_FIELDS = [
  { key: "full_name", label: "Full name" },
  { key: "first_name", label: "First name" },
  { key: "last_name", label: "Last name" },
  { key: "primary_email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "linkedin_url", label: "LinkedIn URL" },
  { key: "company_name", label: "Company" },
  { key: "job_title", label: "Job title" },
  { key: "notes", label: "Notes" },
];

export default function ImportPage() {
  const [step, setStep] = useState("upload"); // upload | map | commit | done
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [campaigns, setCampaigns] = useState([]);
  const [campaignMode, setCampaignMode] = useState("new"); // new | existing
  const [newCampaignName, setNewCampaignName] = useState("");
  const [newCampaignCategory, setNewCampaignCategory] = useState("Introductory");
  const [existingCampaignId, setExistingCampaignId] = useState("");
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState(null);
  const [batches, setBatches] = useState([]);
  const [sheetsStatus, setSheetsStatus] = useState({ configured: false, connected: false });
  const [sheetsList, setSheetsList] = useState([]);
  const [loadingSheets, setLoadingSheets] = useState(false);

  const loadBatches = useCallback(async () => {
    try {
      const { data } = await api.get("/import/batches");
      setBatches(data.items || []);
    } catch (_e) {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    (async () => {
      const [{ data: c }, { data: s }] = await Promise.all([
        api.get("/campaigns"),
        api.get("/sheets/status"),
      ]);
      setCampaigns(c.items || []);
      setSheetsStatus(s);
    })();
    loadBatches();
    // handle callback return
    const p = new URLSearchParams(window.location.search);
    if (p.get("google") === "connected") {
      toast.success("Google account connected");
      api.get("/sheets/status").then(({ data }) => setSheetsStatus(data));
      window.history.replaceState({}, "", "/import");
    }
  }, [loadBatches]);

  const onFile = async (f) => {
    if (!f) return;
    setFile(f);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const { data } = await api.post("/import/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(data);
      setMapping(data.suggested_mapping || {});
      // Default the campaign name to the file name (without extension).
      // The user can still edit or switch to an existing campaign.
      const defaultName = (data.file_name || "").replace(/\.(csv|xlsx|xls)$/i, "").trim();
      setNewCampaignName(defaultName);
      setCampaignMode("new");
      setStep("map");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const commit = async () => {
    if (
      !mapping.primary_email &&
      !mapping.linkedin_url &&
      !mapping.phone &&
      !mapping.full_name &&
      !mapping.first_name &&
      !mapping.last_name
    ) {
      toast.error(
        "Map at least one column (Email, LinkedIn, Phone, or a Name column) to continue."
      );
      return;
    }
    if (campaignMode === "new" && !newCampaignName.trim()) {
      toast.error("Give the campaign a name");
      return;
    }
    if (campaignMode === "existing" && !existingCampaignId) {
      toast.error("Choose an existing campaign");
      return;
    }

    setCommitting(true);
    try {
      const payload = {
        token: preview.token,
        mapping,
        campaign_id: campaignMode === "existing" ? existingCampaignId : null,
        new_campaign_name: campaignMode === "new" ? newCampaignName.trim() : null,
        new_campaign_category: campaignMode === "new" ? newCampaignCategory : null,
      };
      const { data } = await api.post("/import/commit", payload);
      setResult(data);
      setStep("done");
      loadBatches();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Import failed");
    } finally {
      setCommitting(false);
    }
  };

  const reset = () => {
    setStep("upload");
    setFile(null);
    setPreview(null);
    setMapping({});
    setCampaignMode("new");
    setNewCampaignName("");
    setExistingCampaignId("");
    setResult(null);
  };

  const connectGoogle = async () => {
    try {
      const { data } = await api.get("/oauth/sheets/login");
      window.location.href = data.authorization_url;
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Google not configured");
    }
  };

  const loadGoogleSheets = async () => {
    setLoadingSheets(true);
    try {
      const { data } = await api.get("/sheets/list");
      setSheetsList(data.items || []);
    } catch (e) {
      toast.error("Could not list sheets");
    } finally {
      setLoadingSheets(false);
    }
  };

  const previewGoogleSheet = async (spreadsheet_id) => {
    setUploading(true);
    try {
      const { data } = await api.post("/sheets/preview", { spreadsheet_id });
      setPreview({ ...data, kind: "gsheet" });
      setMapping(data.suggested_mapping || {});
      setStep("map");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Preview failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="h-full flex flex-col" data-testid="import-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">Import contacts</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Bring in Excel/CSV files or connect Google Sheets. Duplicates are handled automatically.
        </p>
      </div>

      <div className="flex-1 overflow-auto p-6 max-w-5xl w-full">
        {step === "upload" && (
          <Tabs defaultValue="file" className="w-full">
            <TabsList data-testid="import-source-tabs">
              <TabsTrigger value="file" data-testid="tab-file">
                <UploadCloud className="w-4 h-4 mr-1.5" />
                File upload
              </TabsTrigger>
              <TabsTrigger value="gsheets" data-testid="tab-gsheets">
                <FileSpreadsheet className="w-4 h-4 mr-1.5" />
                Google Sheets
              </TabsTrigger>
              <TabsTrigger value="history" data-testid="tab-history">
                History
              </TabsTrigger>
            </TabsList>

            <TabsContent value="file" className="mt-4">
              <label
                className="flex flex-col items-center justify-center border-2 border-dashed border-slate-300 rounded-md bg-white p-12 hover:border-indigo-400 hover:bg-indigo-50/30 transition-colors cursor-pointer"
                data-testid="file-dropzone"
              >
                <UploadCloud className="w-8 h-8 text-slate-400" />
                <div className="mt-3 text-sm font-medium text-slate-700">
                  Drop your .xlsx or .csv file here
                </div>
                <div className="text-xs text-slate-500 mt-1">or click to browse</div>
                <input
                  type="file"
                  className="hidden"
                  accept=".csv,.xlsx,.xls"
                  onChange={(e) => onFile(e.target.files?.[0])}
                  data-testid="file-input"
                />
                {uploading && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Reading file…
                  </div>
                )}
              </label>
            </TabsContent>

            <TabsContent value="gsheets" className="mt-4">
              <div className="bg-white border border-slate-200 rounded-md p-6">
                {!sheetsStatus.configured ? (
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-500 mt-0.5" />
                    <div className="text-sm text-slate-700">
                      <div className="font-medium">Google Sheets is not yet configured.</div>
                      <div className="text-slate-500 mt-1">
                        An admin needs to add <code className="text-mono">GOOGLE_CLIENT_SECRET</code>{" "}
                        to enable direct spreadsheet import. In the meantime, you can export any
                        Google Sheet as CSV and use the File upload tab.
                      </div>
                    </div>
                  </div>
                ) : !sheetsStatus.connected ? (
                  <div className="text-center">
                    <FileSpreadsheet className="w-10 h-10 text-slate-400 mx-auto" />
                    <div className="mt-2 text-sm font-medium">Connect your Google account</div>
                    <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                      We&apos;ll only request read-only access to your spreadsheets metadata and content.
                    </p>
                    <Button
                      onClick={connectGoogle}
                      className="mt-4 bg-indigo-600 hover:bg-indigo-700 text-white"
                      data-testid="connect-google-btn"
                    >
                      <Link2 className="w-4 h-4 mr-1.5" />
                      Connect Google
                    </Button>
                  </div>
                ) : (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-sm font-medium text-slate-900">Your spreadsheets</div>
                      <Button size="sm" variant="outline" onClick={loadGoogleSheets}>
                        {loadingSheets ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          "Refresh"
                        )}
                      </Button>
                    </div>
                    {sheetsList.length === 0 ? (
                      <div className="text-xs text-slate-500 py-6 text-center">
                        Click &quot;Refresh&quot; to list your Google Sheets.
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100">
                        {sheetsList.map((s) => (
                          <button
                            key={s.id}
                            className="w-full text-left py-2 px-2 hover:bg-slate-50 rounded flex items-center justify-between"
                            onClick={() => previewGoogleSheet(s.id)}
                            data-testid={`gsheet-${s.id}`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                              <div className="truncate text-sm text-slate-800">{s.name}</div>
                            </div>
                            <div className="text-[11px] text-slate-400 text-mono">
                              {new Date(s.modifiedTime).toLocaleDateString()}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="history" className="mt-4">
              <div className="bg-white border border-slate-200 rounded-md divide-y divide-slate-100">
                {batches.length === 0 ? (
                  <div className="text-center text-sm text-slate-400 py-8">
                    No imports yet.
                  </div>
                ) : (
                  batches.map((b) => (
                    <div key={b.id} className="flex items-center justify-between px-4 py-2.5">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-slate-900 truncate">
                          {b.file_name}
                        </div>
                        <div className="text-xs text-slate-500 truncate">
                          → {b.campaign_name || "—"} ·{" "}
                          {b.created_at &&
                            new Date(b.created_at).toLocaleString()}
                        </div>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-600 shrink-0">
                        <StatChip label="new" value={b.stats?.new_people || 0} tone="active" />
                        <StatChip label="matched" value={b.stats?.matched_people || 0} tone="paused" />
                        <StatChip label="dup" value={b.stats?.possible_duplicates || 0} tone="duplicate" />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </TabsContent>
          </Tabs>
        )}

        {step === "map" && preview && (
          <MappingStep
            preview={preview}
            mapping={mapping}
            setMapping={setMapping}
            campaigns={campaigns}
            campaignMode={campaignMode}
            setCampaignMode={setCampaignMode}
            newCampaignName={newCampaignName}
            setNewCampaignName={setNewCampaignName}
            newCampaignCategory={newCampaignCategory}
            setNewCampaignCategory={setNewCampaignCategory}
            existingCampaignId={existingCampaignId}
            setExistingCampaignId={setExistingCampaignId}
            onCancel={reset}
            onCommit={commit}
            committing={committing}
          />
        )}

        {step === "done" && result && (
          <DoneStep result={result} onReset={reset} />
        )}
      </div>
    </div>
  );
}

function StatChip({ label, value, tone }) {
  const cls =
    tone === "active"
      ? "chip chip-active"
      : tone === "duplicate"
      ? "chip chip-duplicate"
      : "chip chip-paused";
  return (
    <div className={cls}>
      <span className="text-mono font-semibold mr-1">{value}</span>
      {label}
    </div>
  );
}

function MappingStep({
  preview,
  mapping,
  setMapping,
  campaigns,
  campaignMode,
  setCampaignMode,
  newCampaignName,
  setNewCampaignName,
  newCampaignCategory,
  setNewCampaignCategory,
  existingCampaignId,
  setExistingCampaignId,
  onCancel,
  onCommit,
  committing,
}) {
  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200 rounded-md p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold">File</div>
            <div className="text-sm font-medium text-slate-900 mt-0.5">
              {preview.file_name}
            </div>
            <div className="text-xs text-slate-500 mt-0.5 text-mono">
              {preview.total_rows} rows · {preview.headers.length} columns
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onCancel} data-testid="import-cancel-btn">
            <X className="w-4 h-4 mr-1" /> Start over
          </Button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-md p-5">
        <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">
          Column mapping
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {STANDARD_FIELDS.map((f) => (
            <div key={f.key}>
              <Label>{f.label}</Label>
              <Select
                value={mapping[f.key] || "__none"}
                onValueChange={(v) => {
                  setMapping((m) => ({
                    ...m,
                    [f.key]: v === "__none" ? undefined : v,
                  }));
                }}
              >
                <SelectTrigger
                  className="mt-1.5"
                  data-testid={`map-${f.key}`}
                >
                  <SelectValue placeholder="— none —" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">— none —</SelectItem>
                  {preview.headers.map((h) => (
                    <SelectItem key={h} value={h}>
                      {h}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>

        <div className="mt-5 pt-4 border-t border-slate-100">
          <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">
            Preview (first 10 rows)
          </div>
          <div className="overflow-x-auto border border-slate-200 rounded-md">
            <table className="text-xs w-full">
              <thead className="bg-slate-50">
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h} className="px-2 py-1.5 text-left text-slate-600 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {preview.preview_rows.map((r, i) => (
                  <tr key={i}>
                    {preview.headers.map((h) => (
                      <td key={h} className="px-2 py-1 text-slate-700 text-mono truncate max-w-[160px]">
                        {r[h]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-md p-5">
        <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">
          Assign to campaign
        </div>
        <div className="flex gap-3 mb-3">
          <button
            data-testid="campaign-mode-new"
            onClick={() => setCampaignMode("new")}
            className={`flex-1 border rounded-md px-3 py-2 text-sm ${
              campaignMode === "new"
                ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                : "border-slate-200 hover:border-slate-300"
            }`}
          >
            Create new campaign
          </button>
          <button
            data-testid="campaign-mode-existing"
            onClick={() => setCampaignMode("existing")}
            className={`flex-1 border rounded-md px-3 py-2 text-sm ${
              campaignMode === "existing"
                ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                : "border-slate-200 hover:border-slate-300"
            }`}
          >
            Add to existing campaign
          </button>
        </div>
        {campaignMode === "new" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label>Campaign name</Label>
              <Input
                value={newCampaignName}
                onChange={(e) => setNewCampaignName(e.target.value)}
                placeholder="e.g. Q2 Broker Outreach"
                data-testid="new-campaign-name-import"
                className="mt-1.5"
              />
            </div>
            <div>
              <Label>Category</Label>
              <Select value={newCampaignCategory} onValueChange={setNewCampaignCategory}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Introductory">Introductory</SelectItem>
                  <SelectItem value="Event">Event</SelectItem>
                  <SelectItem value="Nurture">Nurture</SelectItem>
                  <SelectItem value="Product-specific">Product-specific</SelectItem>
                  <SelectItem value="Other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        ) : (
          <div>
            <Label>Existing campaign</Label>
            <Select value={existingCampaignId} onValueChange={setExistingCampaignId}>
              <SelectTrigger className="mt-1.5" data-testid="existing-campaign-select">
                <SelectValue placeholder="Pick a campaign…" />
              </SelectTrigger>
              <SelectContent>
                {campaigns.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button
          onClick={onCommit}
          disabled={committing}
          className="bg-indigo-600 hover:bg-indigo-700 text-white"
          data-testid="commit-import-btn"
        >
          {committing ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> Importing…
            </>
          ) : (
            <>Import {preview.total_rows} rows</>
          )}
        </Button>
      </div>
    </div>
  );
}

function DoneStep({ result, onReset }) {
  const s = result.stats;
  return (
    <div className="bg-white border border-slate-200 rounded-md p-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="w-8 h-8 text-emerald-500" />
        <div>
          <div className="text-lg font-semibold text-slate-900">Import complete</div>
          <div className="text-sm text-slate-500">
            → Assigned to campaign{" "}
            <span className="font-medium text-slate-800">{result.campaign_name}</span>
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Rows processed" value={s.total_rows} />
        <StatCard label="New people" value={s.new_people} tone="active" />
        <StatCard label="Matched" value={s.matched_people} />
        <StatCard label="Possible duplicates" value={s.possible_duplicates} tone="duplicate" />
      </div>

      {s.possible_duplicates > 0 && (
        <div className="mt-4 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-800">
          <AlertCircle className="w-4 h-4 mt-0.5" />
          <div>
            {s.possible_duplicates} rows matched an existing person by name+company but no hard
            identifier. Review them in the Duplicates queue.
          </div>
        </div>
      )}

      <div className="mt-6 flex gap-2">
        <Button
          onClick={onReset}
          variant="outline"
          data-testid="import-again-btn"
        >
          Import another
        </Button>
        <Button
          onClick={() => (window.location.href = `/people`)}
          className="bg-indigo-600 hover:bg-indigo-700 text-white"
          data-testid="view-people-after-import-btn"
        >
          View directory
        </Button>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }) {
  const border =
    tone === "active"
      ? "border-emerald-200"
      : tone === "duplicate"
      ? "border-amber-200"
      : "border-slate-200";
  const numColor =
    tone === "active"
      ? "text-emerald-700"
      : tone === "duplicate"
      ? "text-amber-700"
      : "text-slate-900";
  return (
    <div className={`bg-white border ${border} rounded-md p-3`}>
      <div className={`text-2xl font-bold text-mono ${numColor}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mt-0.5">
        {label}
      </div>
    </div>
  );
}
