export function CampaignChip({ name, status, onClick, testId }) {
  const cls =
    status === "Active"
      ? "chip chip-active"
      : status === "Paused"
      ? "chip chip-paused"
      : status === "Completed"
      ? "chip chip-completed"
      : "chip chip-active";
  const dotCls =
    status === "Active"
      ? "bg-emerald-500"
      : status === "Paused"
      ? "bg-slate-400"
      : status === "Completed"
      ? "bg-slate-300"
      : "bg-emerald-500";
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`${cls} focus:outline-none focus:ring-1 focus:ring-indigo-400`}
      title={`${name} • ${status || "Active"}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${dotCls}`} />
      <span className="max-w-[140px] overflow-hidden text-ellipsis">{name}</span>
    </button>
  );
}
