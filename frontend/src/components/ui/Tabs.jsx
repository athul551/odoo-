export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((tab) => {
        const selected = tab.id === active
        const classes = selected
          ? 'border-indigo-600 text-indigo-700'
          : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700'
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${classes}`}
          >
            {tab.label}
            {tab.count != null && (
              <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                {tab.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
