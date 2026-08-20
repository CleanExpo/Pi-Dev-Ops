// app/(main)/health/page.tsx — consolidated into /control/health
import { redirect } from "next/navigation";

export default function HealthRedirect(): never {
  redirect("/control/health");
}
