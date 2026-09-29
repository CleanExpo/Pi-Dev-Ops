export function classify(input: { source: string }) {
  if (input.source === "sewage") return { category: 3 };
  if (input.source === "greywater") return { category: 2 };
  return { category: 1 };
}
