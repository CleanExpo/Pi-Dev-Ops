import { ato } from "./ato/index.js";
import { carsi } from "./carsi/index.js";
import { coord } from "./coord/index.js";
import { drnrpg } from "./drnrpg/index.js";
import { missionControl } from "./mission-control/index.js";
import { pidevops } from "./pidevops/index.js";
import { restoreassist } from "./restoreassist/index.js";
import { synthex } from "./synthex/index.js";
import { unite } from "./unite/index.js";

/**
 * The only registration list.
 * Add a project by creating adapters/<id>/index.js and appending it here.
 *
 * Not registered in this version:
 * ccw-crm, disaster-recovery.
 */
export const adapters = [
  coord,
  pidevops,
  unite,
  missionControl,
  restoreassist,
  synthex,
  drnrpg,
  ato,
  carsi,
];
