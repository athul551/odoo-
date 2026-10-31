import { useCallback, useEffect, useState } from 'react'
import Badge from '../ui/Badge'
import Card from '../ui/Card'
import { ErrorBox, Loading } from '../ui/Feedback'
import { EmptyRow, Table, Td, Th, Tr } from '../ui/Table'
import api, { apiError } from '../../lib/api'
import { dateOnly, money, titleize } from '../../lib/format'

export default function PaymentsLedger() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/payments/', { params: { page_size: 200 } })
      setRows(data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const total = rows.reduce((sum, payment) => sum + Number(payment.amount ?? 0), 0)

  return (
    <Card
      title="Payments ledger"
      subtitle="Every receipt attached to an invoice, newest first."
      actions={<Badge tone="ok">Total {money(total)}</Badge>}
      bodyClassName="pb-2"
    >
      <ErrorBox message={error} onRetry={load} />
      {loading ? (
        <Loading />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Invoice</Th>
              <Th>Method</Th>
              <Th>Paid on</Th>
              <Th>Reference</Th>
              <Th>Recorded by</Th>
              <Th className="text-right">Amount</Th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={6}>No payments recorded yet.</EmptyRow>}
            {rows.map((payment) => (
              <Tr key={payment.id}>
                <Td className="font-mono text-xs text-paper">{payment.invoice_number}</Td>
                <Td>{titleize(payment.method)}</Td>
                <Td className="whitespace-nowrap">{dateOnly(payment.paid_on)}</Td>
                <Td>{payment.reference || '—'}</Td>
                <Td className="text-xs text-faint">{payment.recorded_by_email || '—'}</Td>
                <Td className="text-right text-paper">{money(payment.amount)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
