export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      {tabs.map((tab) => {
        const selected = tab.id === active
        const classes = selected
          ? 'border-accent text-accent'
          : 'border-transparent text-secondary hover:border-line hover:text-secondary'
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${classes}`}
          >
            {tab.label}
            {tab.count != null && (
              <span className="ml-1.5 rounded-full bg-raised px-1.5 py-0.5 text-xs text-secondary">
                {tab.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
