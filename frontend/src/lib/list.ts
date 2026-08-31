export function updateItem<T, K extends keyof T>(list: T[], index: number, key: K, value: T[K]): T[] {
  return list.map((item, i) => (i === index ? { ...item, [key]: value } : item));
}

export function removeItem<T>(list: T[], index: number): T[] {
  return list.filter((_, i) => i !== index);
}
