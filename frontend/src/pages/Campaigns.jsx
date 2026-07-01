import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { CampaignChip } from "@/components/CampaignChip";
import {
  Plus,
  Users as UsersIcon,
  Lock,
  Share2,
  ShieldCheck,
  Check,
  X,
  Loader2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function CampaignsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [mine, setMine] = useState([]);
  const [all, setAll] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Introductory");
  const [status, setStatus] = useState("Active");
  const [users, setUsers] = useState([]);
  const [shareOpen, setShareOpen] = useState(null); // campaign object (single-share)
  const [shareUserId, setShareUserId] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkShareOpen, setBulkShareOpen] = useState(false);
  const [bulkShareUserIds, setBulkShareUserIds] = useState([]);
  const [requests, setRequests] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [requestedIds, setRequestedIds] = useState(new Set());

  const load = async () => {
    setLoading(true);
    try {
      const [{ data: my }, { data: all_ }] = await Promise.all([
        api.get("/campaigns", { params: { scope: "mine" } }),
        api.get("/campaigns", { params: { scope: "all" } }),
      ]);
      setMine(my.items || []);
      setAll(all_.items || []);
      if (isAdmin) {
        const { data: uList } = await api.get("/users");
        setUsers(uList.items || []);
        const { data: reqs } = await api.get("/access-requests");
        setRequests(reqs.items || []);
      } else {
        const { data: my_reqs } = await api.get("/my-access-requests");
        setMyRequests(my_reqs.items || []);
        setRequestedIds(
          new Set(
            (my_reqs.items || [])
              .filter((r) => r.status === "pending")
              .map((r) => r.campaign_id)
          )
        );
      }
    } catch (_e) {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [isAdmin]);

  const create = async () => {
    if (!name.trim()) {
      toast.error("Name required");
      return;
    }
    try {
      await api.post("/campaigns", { name, category, status });
      toast.success("Campaign created");
      setName("");
      setOpen(false);
      load();
    } catch (_e) {
      toast.error("Could not create campaign");
    }
  };

  const requestAccess = async (c) => {
    try {
      const { data } = await api.post(`/campaigns/${c.id}/request-access`);
      if (data.already_has_access) toast.info("You already have access");
      else if (data.already_requested) toast.info("Request already pending");
      else toast.success("Access requested — the owner will decide");
      setRequestedIds((prev) => new Set(prev).add(c.id));
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Request failed");
    }
  };

  const shareWith = async () => {
    if (!shareOpen || !shareUserId) return;
    try {
      await api.post(`/campaigns/${shareOpen.id}/share`, { user_ids: [shareUserId] });
      toast.success("Shared");
      setShareOpen(null);
      setShareUserId("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Share failed");
    }
  };

  const unshare = async (campaignId, userId) => {
    try {
      await api.post(`/campaigns/${campaignId}/unshare`, { user_id: userId });
      toast.success("Removed access");
      load();
    } catch (_e) {
      toast.error("Failed");
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

  const runBulkShare = async () => {
    if (selectedIds.size === 0) {
      toast.error("Pick at least one campaign");
      return;
    }
    if (bulkShareUserIds.length === 0) {
      toast.error("Pick at least one teammate");
      return;
    }
    try {
      const { data } = await api.post("/campaigns/bulk-share", {
        campaign_ids: Array.from(selectedIds),
        user_ids: bulkShareUserIds,
      });
      toast.success(
        `Shared ${data.shared.length} campaign${data.shared.length === 1 ? "" : "s"} with ${data.user_ids.length} teammate${data.user_ids.length === 1 ? "" : "s"}` +
          (data.skipped.length ? ` · ${data.skipped.length} skipped (not owner)` : "")
      );
      setBulkShareOpen(false);
      setBulkShareUserIds([]);
      setSelectedIds(new Set());
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Bulk share failed");
    }
  };

  const actOnRequest = async (id, action) => {
    try {
      await api.post(`/access-requests/${id}/action`, { action });
      toast.success(action === "approve" ? "Approved" : "Denied");
      load();
    } catch (_e) {
      toast.error("Failed");
    }
  };

  const inaccessibleCampaigns = all.filter(
    (c) => !c.has_access
  );

  // eslint-disable-next-line react/no-unstable-nested-components
  const CampaignCard = ({ c, mode }) => {
    const requested = requestedIds.has(c.id);
    const isSelected = selectedIds.has(c.id);
    const canBulkSelect = mode !== "locked" && (isAdmin || c.is_owner);
    return (
      <div
        data-testid={`campaign-card-${c.id}`}
        className={`bg-white border rounded-md p-4 transition-all ${
          mode === "locked"
            ? "border-slate-200 opacity-80"
            : `${isSelected ? "border-indigo-500 ring-1 ring-indigo-500" : "border-slate-200 hover:border-indigo-300"} hover:shadow-sm cursor-pointer`
        }`}
        onClick={() => mode !== "locked" && navigate(`/people?in=${c.id}`)}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 flex-1 min-w-0">
            {canBulkSelect && (
              <input
                type="checkbox"
                className="mt-1 rounded accent-indigo-600 cursor-pointer"
                checked={isSelected}
                onChange={() => toggleSelect(c.id)}
                onClick={(e) => e.stopPropagation()}
                data-testid={`select-campaign-${c.id}`}
                title="Select for bulk share"
              />
            )}
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-slate-900 truncate flex items-center gap-1.5">
                {mode === "locked" && <Lock className="w-3 h-3 text-slate-400" />}
                {c.name}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">{c.category || "—"}</div>
            </div>
          </div>
          <CampaignChip name={c.status} status={c.status} />
        </div>

        <div className="mt-3 flex items-center gap-3 text-xs text-slate-600">
          <div className="flex items-center gap-1">
            <UsersIcon className="w-3 h-3 text-slate-400" />
            <span className="text-mono font-medium text-slate-900">
              {c.people_count || 0}
            </span>
            <span className="text-slate-400">people</span>
          </div>
          {c.is_owner && (
            <div className="chip chip-active !text-[10px]">
              <ShieldCheck className="w-2.5 h-2.5 mr-1" />
              Owner
            </div>
          )}
          {c.shared_with_user_ids?.length > 0 && (
            <div className="text-[10.5px] text-slate-500">
              <Share2 className="w-3 h-3 inline mr-0.5" />
              Shared with {c.shared_with_user_ids.length}
            </div>
          )}
        </div>

        {mode !== "locked" && (isAdmin || c.is_owner) && (
          <div className="mt-3 flex gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7"
              onClick={(e) => {
                e.stopPropagation();
                setShareOpen(c);
              }}
              data-testid={`share-campaign-${c.id}`}
            >
              <Share2 className="w-3 h-3 mr-1" /> Share
            </Button>
          </div>
        )}

        {mode === "locked" && (
          <div className="mt-3">
            <Button
              size="sm"
              variant="outline"
              className="text-xs w-full"
              disabled={requested}
              onClick={(e) => {
                e.stopPropagation();
                requestAccess(c);
              }}
              data-testid={`request-access-${c.id}`}
            >
              {requested ? "Request pending" : "Request access"}
            </Button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col" data-testid="campaigns-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Campaigns</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {mine.length} accessible · {mine.filter((c) => c.status === "Active").length}{" "}
            active
            {isAdmin && requests.length > 0 && (
              <span className="ml-2 text-amber-700 font-medium">
                · {requests.length} access request{requests.length > 1 ? "s" : ""} awaiting review
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.size > 0 && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedIds(new Set())}
                data-testid="clear-campaign-selection"
              >
                Clear ({selectedIds.size})
              </Button>
              <Button
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                size="sm"
                onClick={() => setBulkShareOpen(true)}
                data-testid="bulk-share-btn"
              >
                <Share2 className="w-4 h-4 mr-1.5" />
                Share {selectedIds.size} selected
              </Button>
            </>
          )}
          <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="new-campaign-btn"
            >
              <Plus className="w-4 h-4 mr-1.5" /> New campaign
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create campaign</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <Label htmlFor="c-name">Name</Label>
                <Input
                  id="c-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  data-testid="new-campaign-name"
                  placeholder="e.g. Q2 Broker Nurture"
                  className="mt-1.5"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Category</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="mt-1.5" data-testid="new-campaign-category">
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
                <div>
                  <Label>Status</Label>
                  <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger className="mt-1.5">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Active">Active</SelectItem>
                      <SelectItem value="Paused">Paused</SelectItem>
                      <SelectItem value="Completed">Completed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={create}
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                data-testid="create-campaign-btn"
              >
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {isAdmin && requests.length > 0 && (
          <div className="mb-5 bg-amber-50 border border-amber-200 rounded-md p-3">
            <div className="text-xs uppercase tracking-wider text-amber-800 font-semibold mb-2">
              Access requests ({requests.length})
            </div>
            <div className="space-y-2">
              {requests.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between bg-white border border-amber-100 rounded-md px-3 py-2"
                  data-testid={`access-request-${r.id}`}
                >
                  <div className="text-sm">
                    <span className="font-medium text-slate-900">{r.user_name}</span>
                    <span className="text-slate-500">
                      {" "}
                      ({r.user_email}) — wants access to{" "}
                    </span>
                    <span className="font-medium text-slate-900">{r.campaign_name}</span>
                  </div>
                  <div className="flex gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 border-red-200 hover:bg-red-50"
                      onClick={() => actOnRequest(r.id, "deny")}
                      data-testid={`deny-${r.id}`}
                    >
                      <X className="w-3 h-3 mr-1" />
                      Deny
                    </Button>
                    <Button
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-700 text-white"
                      onClick={() => actOnRequest(r.id, "approve")}
                      data-testid={`approve-${r.id}`}
                    >
                      <Check className="w-3 h-3 mr-1" />
                      Approve
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading ? (
          <div className="text-slate-400 text-sm flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : (
          <Tabs defaultValue="mine">
            <TabsList>
              <TabsTrigger value="mine" data-testid="tab-my-campaigns">
                My campaigns ({mine.length})
              </TabsTrigger>
              {!isAdmin && (
                <TabsTrigger value="others" data-testid="tab-other-campaigns">
                  Explore ({inaccessibleCampaigns.length})
                </TabsTrigger>
              )}
            </TabsList>

            <TabsContent value="mine" className="mt-4">
              {mine.length === 0 ? (
                <div className="text-slate-400 text-sm text-center py-16">
                  You don&apos;t have access to any campaigns yet — create one.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {mine.map((c) => (
                    <CampaignCard key={c.id} c={c} mode="normal" />
                  ))}
                </div>
              )}
            </TabsContent>

            {!isAdmin && (
              <TabsContent value="others" className="mt-4">
                {inaccessibleCampaigns.length === 0 ? (
                  <div className="text-slate-400 text-sm text-center py-16">
                    Nothing here — you have access to all campaigns.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {inaccessibleCampaigns.map((c) => (
                      <CampaignCard key={c.id} c={c} mode="locked" />
                    ))}
                  </div>
                )}
              </TabsContent>
            )}
          </Tabs>
        )}
      </div>

      {/* Share dialog */}
      <Dialog open={!!shareOpen} onOpenChange={(o) => !o && setShareOpen(null)}>
        <DialogContent data-testid="share-dialog">
          <DialogHeader>
            <DialogTitle>Share &quot;{shareOpen?.name}&quot;</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Grant access to</Label>
              <Select value={shareUserId} onValueChange={setShareUserId}>
                <SelectTrigger className="mt-1.5" data-testid="share-user-select">
                  <SelectValue placeholder="Pick a teammate…" />
                </SelectTrigger>
                <SelectContent>
                  {users
                    .filter((u) => u.id !== user.id)
                    .filter(
                      (u) =>
                        !(shareOpen?.shared_with_user_ids || []).includes(u.id)
                    )
                    .map((u) => (
                      <SelectItem key={u.id} value={u.id}>
                        {u.name} ({u.email})
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            {(shareOpen?.shared_with_user_ids || []).length > 0 && (
              <div>
                <Label>Already shared with</Label>
                <div className="mt-1.5 space-y-1">
                  {shareOpen.shared_with_user_ids.map((uid) => {
                    const u = users.find((x) => x.id === uid);
                    return (
                      <div
                        key={uid}
                        className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1.5"
                      >
                        <div className="text-sm text-slate-700">
                          {u ? `${u.name} (${u.email})` : uid}
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-slate-400 hover:text-red-600"
                          onClick={() => unshare(shareOpen.id, uid)}
                        >
                          <X className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShareOpen(null)}>
              Close
            </Button>
            <Button
              onClick={shareWith}
              disabled={!shareUserId}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="do-share-btn"
            >
              <Share2 className="w-3.5 h-3.5 mr-1.5" />
              Share
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Share dialog */}
      <Dialog
        open={bulkShareOpen}
        onOpenChange={(o) => {
          if (!o) {
            setBulkShareOpen(false);
            setBulkShareUserIds([]);
          }
        }}
      >
        <DialogContent data-testid="bulk-share-dialog">
          <DialogHeader>
            <DialogTitle>
              Share {selectedIds.size} campaign{selectedIds.size === 1 ? "" : "s"} with teammates
            </DialogTitle>
            <DialogDescription>
              Give the selected teammates read + notes access to every one of
              these campaigns in one go. You can share a campaign only if you
              own it (or you&apos;re an admin) — others will be silently skipped.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Selected campaigns</Label>
              <div className="mt-1.5 max-h-32 overflow-y-auto space-y-1 border border-slate-200 rounded-md p-2 bg-slate-50/50">
                {Array.from(selectedIds).map((cid) => {
                  const c = mine.find((x) => x.id === cid);
                  return (
                    <div
                      key={cid}
                      className="flex items-center justify-between text-sm px-1.5 py-0.5"
                      data-testid={`bulk-share-selected-${cid}`}
                    >
                      <span className="text-slate-700 truncate">
                        {c?.name || cid}
                      </span>
                      <button
                        className="text-slate-300 hover:text-red-500"
                        onClick={() => toggleSelect(cid)}
                        title="Remove"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <Label>Grant access to (multi-select)</Label>
              <div className="mt-1.5 max-h-48 overflow-y-auto space-y-1 border border-slate-200 rounded-md p-2">
                {users.filter((u) => u.id !== user.id).length === 0 ? (
                  <div className="text-xs text-slate-400 py-2 text-center">
                    No other teammates yet — invite from the Team page.
                  </div>
                ) : (
                  users
                    .filter((u) => u.id !== user.id)
                    .map((u) => (
                      <label
                        key={u.id}
                        className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-slate-50 cursor-pointer text-sm"
                        data-testid={`bulk-share-user-${u.id}`}
                      >
                        <input
                          type="checkbox"
                          className="rounded accent-indigo-600"
                          checked={bulkShareUserIds.includes(u.id)}
                          onChange={() =>
                            setBulkShareUserIds((prev) =>
                              prev.includes(u.id)
                                ? prev.filter((x) => x !== u.id)
                                : [...prev, u.id]
                            )
                          }
                        />
                        <span className="flex-1 text-slate-700">{u.name}</span>
                        <span className="text-mono text-[11px] text-slate-400">
                          {u.email}
                        </span>
                      </label>
                    ))
                )}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setBulkShareOpen(false);
                setBulkShareUserIds([]);
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={runBulkShare}
              disabled={bulkShareUserIds.length === 0 || selectedIds.size === 0}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="do-bulk-share-btn"
            >
              <Share2 className="w-3.5 h-3.5 mr-1.5" />
              Share {selectedIds.size} × {bulkShareUserIds.length}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
