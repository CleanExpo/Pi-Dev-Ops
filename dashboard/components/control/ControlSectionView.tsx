"use client";

import type { ComponentType } from "react";
import AgentRolesPanel from "./AgentRolesPanel";
import BuildForm from "./BuildForm";
import ControlPageFrame from "./ControlPageFrame";
import CuratorProposalsPanel from "./CuratorProposalsPanel";
import GoalTicketForm from "./GoalTicketForm";
import HealthGrid from "./HealthGrid";
import MargotAssetsPanel from "./MargotAssetsPanel";
import ModelFabricPanel from "./ModelFabricPanel";
import RoutineTable from "./RoutineTable";
import SpecPipelinePanel from "./SpecPipelinePanel";
import SwarmPanel from "./SwarmPanel";
import TerminalPanel from "./TerminalPanel";
import type { ControlSectionSlug } from "@/lib/control/nav";
import { controlSectionBySlug } from "@/lib/control/nav";

const VIEWS: Record<ControlSectionSlug, ComponentType> = {
  goal: GoalTicketForm,
  swarm: SwarmPanel,
  model: ModelFabricPanel,
  health: HealthGrid,
  roles: AgentRolesPanel,
  build: BuildForm,
  runs: RoutineTable,
  curator: CuratorProposalsPanel,
  margot: MargotAssetsPanel,
  pipeline: SpecPipelinePanel,
  terminal: TerminalPanel,
};

export default function ControlSectionView({ slug }: { slug: ControlSectionSlug }) {
  const item = controlSectionBySlug(slug);
  if (!item) return null;
  const View = VIEWS[slug];
  const narrow = slug === "build";
  return (
    <ControlPageFrame title={item.title} hint={item.blurb}>
      <div className={narrow ? "max-w-xl" : undefined}>
        <View />
      </div>
    </ControlPageFrame>
  );
}
