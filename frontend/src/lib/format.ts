const CURRENCY_MAP: Record<string, string> = {
  EUR: 'EUR',
  USD: 'USD',
  GBP: 'GBP',
  CHF: 'CHF',
};

export function formatCurrency(amount: number, currency: string = 'EUR'): string {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: CURRENCY_MAP[currency] ?? currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

export function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(date);
}

export function formatRelativeTime(isoStr: string): string {
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  const diffMs = now - then;
  const isFuture = diffMs < 0;
  const absDiffSeconds = Math.floor(Math.abs(diffMs) / 1000);

  if (absDiffSeconds < 60) return isFuture ? 'in a moment' : 'just now';
  if (absDiffSeconds < 3600) {
    const mins = Math.floor(absDiffSeconds / 60);
    return isFuture ? `in ${mins} min` : `${mins} min ago`;
  }
  if (absDiffSeconds < 86400) {
    const hours = Math.floor(absDiffSeconds / 3600);
    return isFuture ? `in ${hours}h` : `${hours}h ago`;
  }
  const days = Math.floor(absDiffSeconds / 86400);
  return isFuture ? `in ${days}d` : `${days}d ago`;
}

export function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Bonjour';
  if (hour < 18) return 'Bon après-midi';
  return 'Bonsoir';
}
