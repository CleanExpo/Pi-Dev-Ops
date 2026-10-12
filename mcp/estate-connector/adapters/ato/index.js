import { healthNoteAdapter } from "../http-project.js";

/** ATO. Health defaults to the public site. Notes work either way. */
export const ato = healthNoteAdapter({
  id: "ato",
  title: "ATO",
  registryId: "ato",
  baseEnv: "ATO_BASE_URL",
  tokenEnv: "ATO_BEARER_TOKEN",
  defaultBase: "https://ato-ai.app",
});
