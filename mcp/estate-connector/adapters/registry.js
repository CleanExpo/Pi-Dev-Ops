import { coord } from "./coord/index.js";
import { missionControl } from "./mission-control/index.js";
import { pidevops } from "./pidevops/index.js";
import { unite } from "./unite/index.js";

/**
 * The only registration list.
 * Add a project by creating adapters/<id>/index.js and appending it here.
 *
 * Not registered in this version:
 * restoreassist, synthex, ccw-crm, dr-nrpg, disaster-recovery, ato, carsi.
 */
export const adapters = [coord, pidevops, unite, missionControl];
