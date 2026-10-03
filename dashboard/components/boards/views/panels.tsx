"use client";
// RA-7898 — view #1 of each module: the existing panel, unchanged. Each wrapper
// renders the panel exactly as its page does; only the frame around it is new.

import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";
import FleetTile from "@/components/control/FleetTile";
import HealthGrid from "@/components/control/HealthGrid";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import KillSwitchPanel from "@/components/control/KillSwitchPanel";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import ModelFabricPanel from "@/components/control/ModelFabricPanel";
import PortfolioFocus from "@/components/control/PortfolioFocus";
import SwarmPanel from "@/components/control/SwarmPanel";
import { ProviderUsageCockpit } from "@/components/command-centre/provider-usage/ProviderUsageCockpit";
import { WikiGraphTile } from "@/components/command-centre/wiki-graph/WikiGraphTile";

export function FleetTileView() { return <FleetTile />; }
export function LiveActivityView() { return <LiveActivityFeed />; }
export function IdeaPipelineView() { return <IdeaPipelinePanel />; }
export function PortfolioFocusView() { return <PortfolioFocus />; }
export function SwarmView() { return <SwarmPanel />; }
export function KillSwitchView() { return <KillSwitchPanel />; }
export function ModelFabricView() { return <ModelFabricPanel />; }
export function HealthGridView() { return <HealthGrid />; }
export function CuratorView() { return <CuratorProposalsPanel />; }
/** Provenance-baselined: wrapped from outside, never edited (spec §4.1). */
export function ProviderUsageView() { return <ProviderUsageCockpit />; }
/** Provenance-baselined: wrapped from outside, never edited (spec §4.1). */
export function WikiGraphView() { return <WikiGraphTile />; }
