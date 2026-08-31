export function salaryLabel(min: number | null, max: number | null): string {
  if (!min && !max) return "薪资面议";
  if (min && max) return `${min}k - ${max}k`;
  return `${min || max}k`;
}
