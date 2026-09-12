export type OrderStatus = 'CREATED' | 'PAID' | 'SHIPPED' | 'CANCELLED'

export function orderStatusLabel(status: OrderStatus): string {
  if (status === 'SHIPPED') return 'On the way'
  if (status === 'CANCELLED') return 'Cancelled'
  return status
}

export function canRequestRefund(status: OrderStatus): boolean {
  return status === 'CANCELLED'
}
