export default function Button({ children, className = '', ...props }) {
  return (
    <button className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 ${className}`} {...props}>
      {children}
    </button>
  )
}
