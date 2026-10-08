import { z } from "zod";

export const botField = z
  .string()
  .optional()
  .describe("Bot name. Skip this when the URL (?bot=) or X-Estate-Bot header already names the bot.");

export const systemField = z
  .string()
  .optional()
  .describe("System id: coord, pidevops, unite, or mc.");
