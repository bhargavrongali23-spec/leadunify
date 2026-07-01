import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CampaignChip } from "@/components/CampaignChip";
import { MessageSquare, X, Send, Sparkles, Loader2, ArrowUpRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

const SUGGESTIONS = [
  "Show me everyone from HDFC Bank",
  "Who's in the Non-QM Introductory campaign but not MBA Annual 2026?",
  "Who did we add in the last two weeks?",
  "Which people are in more than one active campaign?",
];

export default function ChatPanel({ open, onClose, onOpenPerson }) {
  const navigate = useNavigate();
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, loading]);

  const send = async (text) => {
    if (!text.trim()) return;
    const userMsg = { role: "user", content: text };
    setHistory((h) => [...h, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await api.post("/chat/query", { message: text });
      const assistantMsg = {
        role: "assistant",
        content: data.answer,
        results: data.results,
        navigate: data.navigate,
        intent: data.intent,
      };
      setHistory((h) => [...h, assistantMsg]);
    } catch (e) {
      setHistory((h) => [
        ...h,
        { role: "assistant", content: "Sorry, I couldn't process that request." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={`fixed inset-0 z-50 ${open ? "" : "pointer-events-none"}`}
      data-testid="chat-panel-overlay"
    >
      <div
        className={`absolute inset-0 bg-slate-900/20 backdrop-blur-[2px] transition-opacity ${
          open ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
      />
      <aside
        className={`absolute right-0 top-0 bottom-0 w-full sm:max-w-lg bg-white border-l border-slate-200 shadow-2xl flex flex-col transform transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        data-testid="chat-panel"
      >
        <div className="border-b border-slate-200 px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center text-white">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-900">Chat Assistant</div>
              <div className="text-[10.5px] text-slate-500 -mt-0.5">Claude Sonnet 4.5</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            data-testid="close-chat"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/40">
          {history.length === 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                Try asking
              </div>
              <div className="space-y-1.5">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    data-testid={`suggestion-${s.slice(0, 12)}`}
                    className="w-full text-left text-sm text-slate-700 bg-white border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40 rounded-md px-3 py-2 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {history.map((m, i) => (
            <MessageBubble
              key={i}
              message={m}
              onOpenPerson={(id) => {
                onOpenPerson?.(id);
                onClose?.();
              }}
              onNavigate={(path) => {
                onClose?.();
                navigate(path);
              }}
            />
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
              Thinking…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-slate-200 p-3 bg-white">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex gap-2"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your contacts…"
              className="flex-1"
              data-testid="chat-input"
            />
            <Button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="chat-send-btn"
            >
              <Send className="w-4 h-4" />
            </Button>
          </form>
        </div>
      </aside>
    </div>
  );
}

function MessageBubble({ message, onOpenPerson, onNavigate }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-indigo-600 text-white rounded-lg rounded-tr-sm px-3 py-2 text-sm shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-2">
      <div className="w-6 h-6 shrink-0 rounded-md bg-indigo-600 text-white flex items-center justify-center mt-0.5">
        <Sparkles className="w-3 h-3" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="bg-white border border-slate-200 rounded-lg rounded-tl-sm px-3 py-2 text-sm text-slate-800 shadow-sm">
          {message.content}
        </div>

        {message.navigate && (
          <button
            onClick={() => onNavigate(message.navigate)}
            className="mt-2 inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 font-medium"
            data-testid="chat-navigate-btn"
          >
            Open {message.navigate} <ArrowUpRight className="w-3 h-3" />
          </button>
        )}

        {message.results?.items && message.results.items.length > 0 && (
          <div className="mt-2 bg-white border border-slate-200 rounded-md overflow-hidden">
            <div className="px-3 py-1.5 border-b border-slate-100 text-[10.5px] uppercase tracking-wider text-slate-500 font-semibold flex items-center justify-between">
              <span>Results ({message.results.total?.toLocaleString?.() || message.results.items.length})</span>
              <button
                onClick={() => onNavigate("/people")}
                className="text-indigo-600 hover:text-indigo-700 normal-case tracking-normal text-[11px]"
              >
                Open full table →
              </button>
            </div>
            <div className="max-h-72 overflow-y-auto divide-y divide-slate-100">
              {message.results.items.map((p) => (
                <button
                  key={p.id}
                  onClick={() => onOpenPerson(p.id)}
                  data-testid={`chat-result-${p.id}`}
                  className="w-full text-left px-3 py-2 hover:bg-slate-50 transition-colors"
                >
                  <div className="text-sm font-medium text-slate-900 truncate">{p.full_name}</div>
                  <div className="text-mono text-[11.5px] text-slate-500 truncate">
                    {p.primary_email}
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    {p.company_name || "—"} · {p.job_title || "—"}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(p.campaigns || []).slice(0, 3).map((c) => (
                      <CampaignChip key={c.id} name={c.name} status={c.status} />
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {message.results?.items && message.results.items.length === 0 && (
          <div className="mt-2 text-xs text-slate-400 italic">
            No people matched that query.
          </div>
        )}
      </div>
    </div>
  );
}
