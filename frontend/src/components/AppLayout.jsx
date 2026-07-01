import { useState, useEffect } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import PersonDetail from "@/components/PersonDetail";
import { api } from "@/lib/api";

// Simple global-ish state via events for opening person detail from anywhere
export const openPersonEvent = new EventTarget();

export function openPerson(personId) {
  openPersonEvent.dispatchEvent(new CustomEvent("open", { detail: personId }));
}

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(false);
  const [personId, setPersonId] = useState(null);
  const [duplicatesCount, setDuplicatesCount] = useState(0);

  useEffect(() => {
    const handler = (e) => setPersonId(e.detail);
    openPersonEvent.addEventListener("open", handler);
    return () => openPersonEvent.removeEventListener("open", handler);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get("/stats/overview");
        if (!cancelled) setDuplicatesCount(data.pending_duplicates || 0);
      } catch (_e) { /* ignore */ }
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="h-screen w-screen overflow-hidden flex bg-slate-50 text-slate-900">
      <Sidebar
        onOpenChat={() => setChatOpen(true)}
        duplicatesCount={duplicatesCount}
      />
      <main className="flex-1 overflow-auto" data-testid="app-main">
        <Outlet />
      </main>

      {personId && (
        <PersonDetail personId={personId} onClose={() => setPersonId(null)} />
      )}

      <ChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        onOpenPerson={(id) => setPersonId(id)}
      />
    </div>
  );
}
