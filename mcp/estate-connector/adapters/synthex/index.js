import { healthNoteAdapter } from "../http-project.js";

/** Synthex. Health defaults to the public site. Notes work either way. */
export const synthex = healthNoteAdapter({
  id: "synthex",
  title: "Synthex",
  registryId: "synthex",
  baseEnv: "SYNTHEX_BASE_URL",
  tokenEnv: "SYNTHEX_BEARER_TOKEN",
  defaultBase: "https://synthex.social",
});
