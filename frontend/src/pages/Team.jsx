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
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { UserPlus, Shield, User, Copy, Trash2, KeyRound, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Navigate } from "react-router-dom";

export default function TeamPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [invitePwd, setInvitePwd] = useState("");
  const [inviting, setInviting] = useState(false);
  const [lastInvited, setLastInvited] = useState(null);

  const isAdmin = user?.role === "admin";

  const load = async () => {
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

  useEffect(() => {
    load();
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
      load();
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
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Update failed");
    }
  };

  const removeUser = async (id, email) => {
    if (!window.confirm(`Remove ${email}? Their owned campaigns transfer to you.`)) return;
    try {
      await api.delete(`/users/${id}`);
      toast.success("User removed");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Delete failed");
    }
  };

  const resetPassword = async (id, email) => {
    const newPwd = window.prompt(`Set a new temporary password for ${email}:`);
    if (!newPwd) return;
    try {
      await api.patch(`/users/${id}`, { password: newPwd });
      toast.success("Password reset");
    } catch (_e) {
      toast.error("Reset failed");
    }
  };

  return (
    <div className="h-full flex flex-col" data-testid="team-page">
      <div className="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Team</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Invite teammates and control who can do what.
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
                    Share these credentials securely. This is the only time you&apos;ll
                    see the temporary password.
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
                    <div className="flex-1 text-mono text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
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

      <div className="flex-1 overflow-auto p-6 max-w-3xl w-full">
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : users.length === 0 ? (
          <div className="text-slate-400 text-sm">No teammates yet — invite someone!</div>
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
                      <SelectValue placeholder="Change" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="member">Member</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => resetPassword(u.id, u.email)}
                    className="text-slate-400 hover:text-indigo-600"
                    data-testid={`reset-pwd-${u.id}`}
                    title="Reset password"
                  >
                    <KeyRound className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeUser(u.id, u.email)}
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
      </div>
    </div>
  );
}
