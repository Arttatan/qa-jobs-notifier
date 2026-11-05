import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { CV_FILE_NAME, candidateProfile } from "../lib/profile.js";

const inputSchema = z.object({
  title: z.string().min(2).max(180),
  company: z.string().min(1).max(180),
  url: z.string().url(),
  userConfirmed: z.literal(true),
});

type PrepareInput = z.infer<typeof inputSchema>;

function packet(input: PrepareInput, remembered: boolean) {
  return {
    ready: true,
    submitted: false,
    remembered,
    cvFile: CV_FILE_NAME,
    vacancy: {
      title: input.title,
      company: input.company,
      url: input.url,
    },
    profile: candidateProfile,
    letterRules: [
      "Write 160 to 220 words in the language of the vacancy. Use English when the language is unknown.",
      "Use only facts from profile. Do not add employers, tools, dates, or metrics.",
      "He has not worked as a Project Manager. Do not give him that title.",
      "Match two facts to this vacancy title.",
      "Sign with name, email, phone, and LinkedIn.",
      "Tell Artem, in Russian, to attach the CV file himself. Say the application was not submitted.",
    ],
  };
}

export default defineTool({
  description:
    "Load Artem's CV facts for one vacancy he has already accepted. Call this only after he says yes to that exact role. This does not submit an application or send a message.",
  effect: "idempotent",
  inputSchema,
  dryRunResult: (input) => packet(input, false),
  async execute(input, ctx) {
    const key = `job-prepared:v1:${ctx.session.id}:${input.url}`;
    let remembered = false;
    try {
      await ctx.host.kv.put(key, {
        title: input.title,
        company: input.company,
        url: input.url,
      });
      remembered = true;
    } catch {
      remembered = false;
    }
    return packet(input, remembered);
  },
});
