import { healthNoteAdapter } from "../http-project.js";

/** DR-NRPG. Health defaults to the public platform. Notes work either way. */
export const drnrpg = healthNoteAdapter({
  id: "drnrpg",
  title: "DR-NRPG",
  registryId: "dr-nrpg",
  baseEnv: "DRNRPG_BASE_URL",
  tokenEnv: "DRNRPG_BEARER_TOKEN",
  defaultBase: "https://dr-nrpg-platform.vercel.app",
});
