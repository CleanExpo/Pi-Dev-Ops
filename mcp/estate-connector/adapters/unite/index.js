import { httpProjectAdapter } from "../http-project.js";

/** Unite-Group. Live reads wait for UNITE_BASE_URL. Notes work without it. */
export const unite = httpProjectAdapter({
  id: "unite",
  title: "Unite-Group",
  prefix: "unite",
  registryId: "unite-group",
  baseEnv: "UNITE_BASE_URL",
  tokenEnv: "UNITE_BEARER_TOKEN",
  statusPathEnv: "UNITE_STATUS_PATH",
  statusPathDefault: "/api/health",
  projectsPathEnv: "UNITE_PROJECTS_PATH",
});
