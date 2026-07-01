import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  UserPlus,
  Shield,
  User,
  Copy,
  Trash2,
  KeyRound,
  Loader2,
  GitMerge,
  Building2,
  Users as UsersIcon,
  Clock,
  ScrollText,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Navigate } from "react-router-dom";

export default function TeamPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [invitePwd, setInvitePwd] = useState("");
  const [inviting, setInviting] = useState(false);
  const [lastInvited, setLastInvited] = useState(null);

  // Reset-password dialog state
  const [resetUser, setResetUser] = useState(null);
  const [resetPwd, setResetPwd] = useState("");
  const [resetting, setResetting] = useState(false);

  // Delete-user dialog state
  const [deleteUser, setDeleteUser] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Audit log
  const [auditLog, setAuditLog] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  const loadUsers = async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const { data } = await api.get("/users");
      setUsers(data.items || []);
    } catch (_e) {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const loadAudit = async () => {
    if (!isAdmin) return;
    setLoadingAudit(true);
    try {
      const { data } = await api.get("/audit-log", { params: { limit: 100 } });
      setAuditLog(data.items || []);
    } catch (_e) {
      /* ignore */
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    loadUsers();
    loadAudit();
  }, [isAdmin]);

  if (user && !isAdmin) {
    return <Navigate to="/people" replace />;
  }

  const invite = async () => {
    setInviting(true);
    try {
      const { data } = await api.post("/users/invite", {
        email: inviteEmail.trim(),
        name: inviteName.trim() || undefined,
        role: inviteRole,
        password: invitePwd.trim() || undefined,
      });
      setLastInvited(data);
      toast.success(`Invited ${data.user.email}`);
      setInviteEmail("");
      setInviteName("");
      setInvitePwd("");
      loadUsers();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Invite failed");
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (id, role) => {
    try {
      await api.patch(`/users/${id}`, { role });
      toast.success("Role updated");
      loadUsers();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Update failed");
    }
  };

  const openReset = (u) => {
    setResetUser(u);
    setResetPwd("");
  };

  const doReset = async () => {
    if (!resetUser || !resetPwd.trim()) {
      toast.error("Enter a new password");
      return;
    }
    setResetting(true);
    try {
      await api.patch(`/users/${resetUser.id}`, { password: resetPwd });
      toast.success(`Password reset for ${resetUser.email}`);
      setResetUser(null);
      setResetPwd("");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Reset failed");
    } finally {
      setResetting(false);
    }
  };

  const doDelete = async () => {
    if (!deleteUser) return;
    setDeleting(true);
    try {
      await api.delete(`/users/${deleteUser.id}`);
      toast.success(`Removed ${deleteUser.email}`);
      setDeleteUser(null);
      loadUsers();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const genPwd = () => {
    // 12-char base64url-ish password
    const buf = new Uint8Array(9);
    crypto.getRandomValues(buf);
    const b64 = btoa(String.fromCharCode(...buf))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    setResetPwd(b64);
  };

  return (
    <div className="h-full flex flex-col" data-testid="team-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Team</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Invite teammates and see who did what.
          </p>
        </div>
        <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
          <Button
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
            data-testid="invite-user-btn"
            onClick={() => {
              setLastInvited(null);
              setInviteOpen(true);
            }}
          >
            <UserPlus className="w-4 h-4 mr-1.5" /> Invite teammate
          </Button>
          <DialogContent data-testid="invite-dialog">
            <DialogHeader>
              <DialogTitle>Invite a teammate</DialogTitle>
            </DialogHeader>
            {lastInvited ? (
              <div className="space-y-3">
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md">
                  <div className="text-sm font-medium text-emerald-800">
                    {lastInvited.user.email} invited
                  </div>
                  <div className="text-xs text-emerald-700 mt-1">
                    Share these credentials securely. This is the only time
                    you&apos;ll see the temporary password.
                  </div>
                </div>
                <div>
                  <Label>Email</Label>
                  <div className="text-mono text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-2 mt-1">
                    {lastInvited.user.email}
                  </div>
                </div>
                <div>
                  <Label>Temporary password</Label>
                  <div className="flex gap-2 mt-1">
                    <div
                      className="flex-1 text-mono text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-2"
                      data-testid="invited-temp-password"
                    >
                      {lastInvited.temporary_password}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(lastInvited.temporary_password);
                        toast.success("Copied");
                      }}
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <Label htmlFor="inv-email">Email</Label>
                  <Input
                    id="inv-email"
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="teammate@company.com"
                    className="mt-1.5 text-mono"
                    data-testid="invite-email-input"
                  />
                </div>
                <div>
                  <Label htmlFor="inv-name">Name (optional)</Label>
                  <Input
                    id="inv-name"
                    value={inviteName}
                    onChange={(e) => setInviteName(e.target.value)}
                    placeholder="Alex Rivera"
                    className="mt-1.5"
                    data-testid="invite-name-input"
                  />
                </div>
                <div>
                  <Label>Role</Label>
                  <Select value={inviteRole} onValueChange={setInviteRole}>
                    <SelectTrigger className="mt-1.5" data-testid="invite-role-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="member">
                        Member — creates own campaigns, requests access to others
                      </SelectItem>
                      <SelectItem value="admin">
                        Admin — full access to everything
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="inv-pwd">Temporary password (optional)</Label>
                  <Input
                    id="inv-pwd"
                    value={invitePwd}
                    onChange={(e) => setInvitePwd(e.target.value)}
                    placeholder="Leave blank to auto-generate"
                    className="mt-1.5 text-mono"
                    data-testid="invite-password-input"
                  />
                </div>
              </div>
            )}
            <DialogFooter>
              {lastInvited ? (
                <Button
                  onClick={() => setInviteOpen(false)}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  data-testid="close-invite-dialog"
                >
                  Done
                </Button>
              ) : (
                <>
                  <Button variant="outline" onClick={() => setInviteOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    onClick={invite}
                    disabled={inviting || !inviteEmail.trim()}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    data-testid="send-invite-btn"
                  >
                    {inviting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Invite"}
                  </Button>
                </>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex-1 overflow-auto p-6 max-w-4xl w-full">
        <Tabs defaultValue="members">
          <TabsList>
            <TabsTrigger value="members" data-testid="tab-team-members">
              <UsersIcon className="w-4 h-4 mr-1.5" />
              Members ({users.length})
            </TabsTrigger>
            <TabsTrigger value="audit" data-testid="tab-audit-log">
              <ScrollText className="w-4 h-4 mr-1.5" />
              Audit log ({auditLog.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="members" className="mt-4">
            {loading ? (
              <div className="text-slate-400 text-sm">Loading…</div>
            ) : users.length === 0 ? (
              <div className="text-slate-400 text-sm">
                No teammates yet — invite someone!
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-md divide-y divide-slate-100">
                {users.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center gap-3 px-4 py-3"
                    data-testid={`user-row-${u.id}`}
                  >
                    <div
                      className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold shrink-0 ${
                        u.role === "admin"
                          ? "bg-indigo-100 text-indigo-700"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {(u.name || u.email).slice(0, 1).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-slate-900 truncate">
                        {u.name || u.email.split("@")[0]}
                      </div>
                      <div className="text-mono text-[12px] text-slate-500 truncate">
                        {u.email}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div
                        className={`chip ${
                          u.role === "admin" ? "chip-active" : "chip-paused"
                        }`}
                      >
                        {u.role === "admin" ? (
                          <Shield className="w-3 h-3 mr-1" />
                        ) : (
                          <User className="w-3 h-3 mr-1" />
                        )}
                        {u.role}
                      </div>
                      <Select
                        value={u.role}
                        onValueChange={(v) => changeRole(u.id, v)}
                        disabled={u.id === user.id}
                      >
                        <SelectTrigger
                          className="h-8 text-xs w-24"
                          data-testid={`role-select-${u.id}`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="member">Member</SelectItem>
                          <SelectItem value="admin">Admin</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openReset(u)}
                        className="text-slate-400 hover:text-indigo-600"
                        data-testid={`reset-pwd-${u.id}`}
                        title="Reset password"
                      >
                        <KeyRound className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setDeleteUser(u)}
                        disabled={u.id === user.id}
                        className="text-slate-400 hover:text-red-600"
                        data-testid={`remove-user-${u.id}`}
                        title="Remove user"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="audit" className="mt-4">
            {loadingAudit ? (
              <div className="text-slate-400 text-sm">Loading…</div>
            ) : auditLog.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-md p-8 text-center">
                <ScrollText className="w-10 h-10 text-slate-300 mx-auto" />
                <div className="mt-3 text-sm font-medium text-slate-900">
                  Nothing logged yet
                </div>
                <div className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                  Merges and other destructive actions will appear here with who
                  did what, when.
                </div>
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-md divide-y divide-slate-100">
                {auditLog.map((entry) => (
                  <AuditRow key={entry.id} entry={entry} />
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Reset password dialog */}
      <Dialog open={!!resetUser} onOpenChange={(o) => !o && setResetUser(null)}>
        <DialogContent data-testid="reset-password-dialog">
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
            <DialogDescription>
              Set a new temporary password for{" "}
              <span className="text-mono">{resetUser?.email}</span>. Share it
              with them securely — they can log in with it immediately.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="reset-pwd">New temporary password</Label>
              <div className="flex gap-2 mt-1.5">
                <Input
                  id="reset-pwd"
                  value={resetPwd}
                  onChange={(e) => setResetPwd(e.target.value)}
                  placeholder="min 6 characters"
                  className="text-mono"
                  autoFocus
                  data-testid="reset-password-input"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={genPwd}
                  data-testid="reset-password-generate"
                >
                  Generate
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setResetUser(null)}
              disabled={resetting}
            >
              Cancel
            </Button>
            <Button
              onClick={doReset}
              disabled={resetting || !resetPwd.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="reset-password-confirm"
            >
              {resetting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <KeyRound className="w-3.5 h-3.5 mr-1.5" />
                  Reset password
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete user dialog */}
      <Dialog open={!!deleteUser} onOpenChange={(o) => !o && setDeleteUser(null)}>
        <DialogContent data-testid="delete-user-dialog">
          <DialogHeader>
            <DialogTitle>Remove {deleteUser?.email}?</DialogTitle>
            <DialogDescription>
              Their account will be deleted. Any campaigns they own will be
              re-assigned to you. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteUser(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              onClick={doDelete}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700 text-white"
              data-testid="delete-user-confirm"
            >
              {deleting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Remove user
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AuditRow({ entry }) {
  const isCompanyMerge = entry.action === "merge_companies";
  const isPeopleMerge = entry.action === "merge_people";
  const Icon = isCompanyMerge ? Building2 : GitMerge;
  const label = isCompanyMerge
    ? "Merged companies"
    : isPeopleMerge
    ? "Merged people"
    : entry.action;

  const dt = entry.created_at ? new Date(entry.created_at) : null;
  const d = entry.detail || {};

  return (
    <div className="px-4 py-3 flex items-start gap-3" data-testid={`audit-row-${entry.id}`}>
      <div className="w-8 h-8 rounded-md bg-slate-100 flex items-center justify-center text-slate-500 shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-900">
          <span className="font-medium">{label}</span>
          {isCompanyMerge && (
            <>
              {" "}— kept{" "}
              <span className="font-medium">{d.kept_name}</span>, moved{" "}
              <span className="text-mono">{d.people_moved || 0}</span>{" "}
              {(d.people_moved || 0) === 1 ? "person" : "people"}
            </>
          )}
          {isPeopleMerge && (
            <>
              {" "}— kept <span className="font-medium">{d.kept_name}</span>{" "}
              (<span className="text-mono">{d.kept_email}</span>), removed{" "}
              <span className="font-medium">{d.merged_name}</span>
            </>
          )}
        </div>
        <div className="text-[11.5px] text-slate-500 mt-0.5 flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          {dt ? dt.toLocaleString() : "—"}
          <span className="text-slate-300">·</span>
          <span className="text-mono">{entry.performed_by_email || "system"}</span>
        </div>
      </div>
    </div>
  );
}
