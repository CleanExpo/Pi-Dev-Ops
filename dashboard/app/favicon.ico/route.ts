export function GET() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="#0a0a0a"/>
<text x="32" y="43" text-anchor="middle" font-family="Arial, sans-serif" font-size="36" font-weight="700" fill="#f97316">π</text>
</svg>`;

  return new Response(svg, {
    headers: {
      "Cache-Control": "public, max-age=86400",
      "Content-Type": "image/svg+xml",
    },
  });
}
