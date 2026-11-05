import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { searchQaJobs } from "../lib/jobs.js";

export default defineTool({
  description:
    "Find remote QA, QA automation, SDET, and AI-QA vacancies from public company job boards. Return links for Artem to review. This does not submit an application.",
  effect: "read",
  inputSchema: z.object({
    limit: z.number().int().min(1).max(6).optional(),
  }),
  async execute({ limit }) {
    const found = await searchQaJobs(limit ?? 5);
    return {
      submitted: false,
      jobs: found.jobs,
      failedSources: found.failedSources,
      scannedSources: found.scannedSources,
    };
  },
});
