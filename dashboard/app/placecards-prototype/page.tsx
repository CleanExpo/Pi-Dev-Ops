import type { Metadata } from "next";
import { PlacecardsPrototype } from "@/components/placecards/PlacecardsPrototype";

export const metadata: Metadata = {
  title: "Placecards — Pi CEO",
  description: "Idea-maturation board. Decisions are recorded, not executed.",
};

export default function PlacecardsPrototypePage() {
  return <PlacecardsPrototype />;
}
