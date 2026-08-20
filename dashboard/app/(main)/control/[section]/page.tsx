import { notFound } from "next/navigation";
import ControlSectionView from "@/components/control/ControlSectionView";
import {
  CONTROL_SECTIONS,
  controlSectionBySlug,
  isControlSectionSlug,
} from "@/lib/control/nav";

export function generateStaticParams(): Array<{ section: string }> {
  return CONTROL_SECTIONS.map((item) => ({ section: item.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  const item = controlSectionBySlug(section);
  return { title: item ? `${item.title} · Control` : "Control" };
}

export default async function ControlSectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!isControlSectionSlug(section)) notFound();
  return <ControlSectionView slug={section} />;
}
