import { healthNoteAdapter } from "../http-project.js";

/** CARSI. Health defaults to the public site. Notes work either way. */
export const carsi = healthNoteAdapter({
  id: "carsi",
  title: "CARSI",
  registryId: "carsi",
  baseEnv: "CARSI_BASE_URL",
  tokenEnv: "CARSI_BEARER_TOKEN",
  defaultBase: "https://carsi.com.au",
});
