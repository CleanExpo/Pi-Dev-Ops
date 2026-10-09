import { healthNoteAdapter } from "../http-project.js";

/** RestoreAssist. Health defaults to the public site. Notes work either way. */
export const restoreassist = healthNoteAdapter({
  id: "restoreassist",
  title: "RestoreAssist",
  registryId: "restoreassist",
  baseEnv: "RESTOREASSIST_BASE_URL",
  tokenEnv: "RESTOREASSIST_BEARER_TOKEN",
  defaultBase: "https://restoreassist.app",
});
