import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Building2,
  Send,
  Upload,
  GitMerge,
  MessageSquare,
  LogOut,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/people", label: "People", icon: Users, testId: "nav-people" },
  { to: "/companies", label: "Companies", icon: Building2, testId: "nav-companies" },
  { to: "/campaigns", label: "Campaigns", icon: Send, testId: "nav-campaigns" },
  { to: "/import", label: "Import", icon: Upload, testId: "nav-import" },
  { to: "/duplicates", label: "Duplicates", icon: GitMerge, testId: "nav-duplicates" },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, testId: "nav-dashboard" },
];

export default function Sidebar({ onOpenChat, duplicatesCount = 0 }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <aside
      data-testid="app-sidebar"
      className="w-60 shrink-0 border-r border-slate-200 bg-white flex flex-col"
    >
      <div className="px-5 pt-6 pb-5 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-indigo-600 flex items-center justify-center text-white shadow-sm">
            <Sparkles className="w-4 h-4" strokeWidth={2.4} />
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-slate-900 leading-none">
              Vaultedge
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Outreach Hub</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              className={`group flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium transition-colors ${
                active
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
              }`}
            >
              <Icon
                className={`w-4 h-4 ${active ? "text-indigo-600" : "text-slate-400 group-hover:text-slate-600"}`}
                strokeWidth={2}
              />
              <span className="flex-1">{item.label}</span>
              {item.to === "/duplicates" && duplicatesCount > 0 && (
                <span
                  data-testid="nav-duplicates-count"
                  className="chip chip-duplicate !py-0 !px-1.5 !text-[10px]"
                >
                  {duplicatesCount}
                </span>
              )}
            </NavLink>
          );
        })}

        <div className="mt-4 border-t border-slate-100 pt-3">
          <button
            data-testid="open-chat-btn"
            onClick={onOpenChat}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium text-slate-600 hover:text-indigo-700 hover:bg-indigo-50 transition-colors"
          >
            <MessageSquare className="w-4 h-4 text-slate-400" strokeWidth={2} />
            <span className="flex-1 text-left">Chat Assistant</span>
            <span className="chip chip-active !py-0 !px-1.5 !text-[10px]">AI</span>
          </button>
        </div>
      </nav>

      <div className="border-t border-slate-200 p-3">
        <div className="flex items-center gap-2.5 px-2 py-1.5">
          <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-[13px] font-semibold text-slate-700">
            {(user?.name || user?.email || "U").slice(0, 1).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium text-slate-900 truncate">
              {user?.name || "User"}
            </div>
            <div className="text-mono text-[11px] text-slate-500 truncate">
              {user?.email}
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            data-testid="logout-btn"
            className="text-slate-400 hover:text-red-600"
            onClick={logout}
          >
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
