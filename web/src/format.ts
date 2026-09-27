/* Anzeigeformate. Alles, was ein Mensch liest, entsteht hier — damit derselbe
   Wert auf jeder Seite gleich aussieht. Zeitangaben liefert der Server bereits
   im deutschen Format (eiserne Regel 9). */

const numberFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 3 })

/** Messwert mit Einheit; Text, wenn es keine Zahl ist. */
export function fmtValue(value: number | null, text: string | null, unit: string | null): string {
  if (value === null) return text ?? '–'
  const shown = numberFormat.format(value)
  // on/off wird zusätzlich als 1/0 gespeichert – angezeigt wird der Text.
  if (text) return text
  return unit ? `${shown} ${unit}` : shown
}

export function fmtBytes(bytes: number | null): string {
  if (bytes === null) return '–'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(value)} ${units[unit]}`
}

export function fmtCount(value: number): string {
  return new Intl.NumberFormat('de-DE').format(value)
}
