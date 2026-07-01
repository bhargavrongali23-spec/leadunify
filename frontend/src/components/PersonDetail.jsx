import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CampaignChip } from "@/components/CampaignChip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Loader2, Mail, Phone, Linkedin, X, Building2, Briefcase, Copy, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function PersonDetail({ personId, onClose }) {
  const [person, setPerson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState("");
  const [campaigns, setCampaigns] = useState([]);
  const [addingCampaign, setAddingCampaign] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);

  useEffect(() => {
    if (!personId) return;
    const load = async () => {
      setLoading(true);
      try {
        const [{ data: p }, { data: c }] = await Promise.all([
          api.get(`/people/${personId}`),
          api.get("/campaigns"),
        ]);
        setPerson(p);
        setNotes(p.notes || "");
        setCampaigns(c.items || []);
      } catch (_e) {
        toast.error("Could not load person");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [personId]);

  const reload = async () => {
    try {
      const { data: p } = await api.get(`/people/${personId}`);
      setPerson(p);
      setNotes(p.notes || "");
    } catch (_e) { /* ignore */ }
  };

  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      const { data } = await api.patch(`/people/${personId}`, { notes });
      setPerson(data);
      toast.success("Notes saved");
    } catch (_e) {
      toast.error("Save failed");
    } finally {
      setSavingNotes(false);
    }
  };

  const removeCampaign = async (campaignId) => {
    await api.delete(`/people/${personId}/campaigns/${campaignId}`);
    reload();
    toast.success("Removed from campaign");
  };

  const addCampaign = async () => {
    if (!addingCampaign) return;
    try {
      const { data } = await api.post(`/people/${personId}/campaigns`, {
        campaign_id: addingCampaign,
      });
      if (data.already_in) {
        toast.info("Already in that campaign");
      } else if (data.other_campaigns?.length) {
        toast.warning(
          `Added. Note: this person is also in ${data.other_campaigns.slice(0, 3).join(", ")}${
            data.other_campaigns.length > 3 ? "…" : ""
          }`
        );
      } else {
        toast.success("Added to campaign");
      }
      setAddingCampaign("");
      reload();
    } catch (_e) {
      toast.error("Add failed");
    }
  };

  const copyEmail = () => {
    if (!person?.primary_email) return;
    navigator.clipboard.writeText(person.primary_email);
    toast.success("Email copied");
  };

  return (
    <div className="fixed inset-0 z-40" data-testid="person-detail-overlay">
      <div
        className="absolute inset-0 bg-slate-900/20 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <aside
        className="absolute right-0 top-0 bottom-0 w-full sm:max-w-md bg-white border-l border-slate-200 shadow-2xl overflow-y-auto slide-panel"
        data-testid="person-detail-panel"
      >
        <div className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200 px-5 py-3 flex items-center justify-between">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
            Person
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            data-testid="close-person-detail"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading || !person ? (
          <div className="flex items-center justify-center p-10 text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Identity */}
            <div>
              <h2 className="text-xl font-bold tracking-tight text-slate-900" data-testid="person-name">
                {person.full_name}
              </h2>
              {person.job_title && (
                <div className="text-sm text-slate-600 mt-0.5 flex items-center gap-1.5">
                  <Briefcase className="w-3.5 h-3.5 text-slate-400" />
                  {person.job_title}
                </div>
              )}
              {person.company_name && (
                <div className="text-sm text-slate-600 mt-1 flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-slate-400" />
                  {person.company_name}
                </div>
              )}
            </div>

            {/* Contacts */}
            <div className="space-y-2">
              <div className="flex items-start gap-2 text-sm">
                <Mail className="w-3.5 h-3.5 text-slate-400 mt-1" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 group">
                    <a
                      href={`mailto:${person.primary_email}`}
                      className="text-mono text-slate-700 hover:text-indigo-700 truncate"
                      data-testid="person-email"
                    >
                      {person.primary_email}
                    </a>
                    <button
                      onClick={copyEmail}
                      className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-slate-600 transition-opacity"
                    >
                      <Copy className="w-3 h-3" />
                    </button>
                  </div>
                  {(person.additional_emails || []).map((e) => (
                    <div key={e} className="text-mono text-xs text-slate-500 truncate">
                      {e}
                    </div>
                  ))}
                </div>
              </div>
              {(person.phones || []).map((ph) => (
                <div key={ph} className="flex items-center gap-2 text-sm">
                  <Phone className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-mono text-slate-700">{ph}</span>
                </div>
              ))}
              {person.linkedin_url && (
                <div className="flex items-center gap-2 text-sm">
                  <Linkedin className="w-3.5 h-3.5 text-slate-400" />
                  <a
                    href={person.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 hover:underline truncate"
                  >
                    View profile
                  </a>
                </div>
              )}
            </div>

            {/* Campaigns */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  Campaigns ({(person.campaigns || []).length})
                </div>
              </div>
              <div className="space-y-1.5">
                {(person.campaigns || []).map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1.5"
                    data-testid={`person-campaign-${c.id}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <CampaignChip name={c.name} status={c.status} />
                    </div>
                    <button
                      className="text-slate-300 hover:text-red-500"
                      onClick={() => removeCampaign(c.id)}
                      data-testid={`remove-campaign-${c.id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
                {(person.campaigns || []).length === 0 && (
                  <div className="text-xs text-slate-400 italic">Not in any campaign yet.</div>
                )}
              </div>

              <div className="mt-3 flex gap-2">
                <Select value={addingCampaign} onValueChange={setAddingCampaign}>
                  <SelectTrigger className="h-8 text-sm" data-testid="add-campaign-select">
                    <SelectValue placeholder="Add to campaign…" />
                  </SelectTrigger>
                  <SelectContent>
                    {campaigns
                      .filter(
                        (c) => !(person.campaigns || []).some((pc) => pc.id === c.id)
                      )
                      .map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  onClick={addCampaign}
                  disabled={!addingCampaign}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white h-8"
                  data-testid="add-campaign-btn"
                >
                  <Plus className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>

            {/* Sources */}
            {(person.sources || []).length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                  Source sheets
                </div>
                <div className="space-y-0.5">
                  {person.sources.map((s, i) => (
                    <div key={i} className="text-xs text-slate-500 text-mono truncate">
                      {s.source_name}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Notes */}
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                Notes
              </div>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add context, meeting notes, warm intros…"
                rows={4}
                className="text-sm"
                data-testid="person-notes-input"
              />
              <Button
                size="sm"
                onClick={saveNotes}
                disabled={savingNotes || notes === (person.notes || "")}
                className="mt-2 bg-indigo-600 hover:bg-indigo-700 text-white"
                data-testid="save-notes-btn"
              >
                {savingNotes ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Save notes"}
              </Button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
