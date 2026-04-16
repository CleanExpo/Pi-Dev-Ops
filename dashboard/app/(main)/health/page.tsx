// app/(main)/health/page.tsx — consolidated into /control (RA-1092)
import { redirect } from "next/navigation";

export default function HealthRedirect(): never {
  redirect("/control");
}
