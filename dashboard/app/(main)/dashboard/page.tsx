// app/(main)/dashboard/page.tsx — consolidated into /control (RA-1092)
import { redirect } from "next/navigation";

export default function DashboardRedirect(): never {
  redirect("/control");
}
