import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
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
import { CampaignChip } from "@/components/CampaignChip";
import { Plus, Users as UsersIcon, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

export default function CampaignsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Introductory");
  const [status, setStatus] = useState("Active");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/campaigns");
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

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
    } catch (_) {
      toast.error("Could not create campaign");
    }
  };

  return (
    <div className="h-full flex flex-col" data-testid="campaigns-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Campaigns</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {items.length} campaigns · {items.filter((c) => c.status === "Active").length} active
          </p>
        </div>
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
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
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

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-slate-400 text-sm text-center py-16">
            No campaigns yet — create one to organize your outreach.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {items.map((c) => (
              <button
                key={c.id}
                data-testid={`campaign-card-${c.id}`}
                onClick={() => navigate(`/people?in=${c.id}`)}
                className="text-left bg-white border border-slate-200 rounded-md p-4 hover:border-indigo-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-900 truncate">{c.name}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{c.category || "—"}</div>
                  </div>
                  <CampaignChip name={c.status} status={c.status} />
                </div>
                <div className="mt-4 flex items-center gap-4 text-xs text-slate-600">
                  <div className="flex items-center gap-1">
                    <UsersIcon className="w-3 h-3 text-slate-400" />
                    <span className="text-mono font-medium text-slate-900">
                      {c.people_count || 0}
                    </span>
                    <span className="text-slate-400">people</span>
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
