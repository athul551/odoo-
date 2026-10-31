export default function Button({ children, className = '', ...props }) {
  return (
    <button className={`primary-button ${className}`} {...props}>
      {children}
    </button>
  )
}
