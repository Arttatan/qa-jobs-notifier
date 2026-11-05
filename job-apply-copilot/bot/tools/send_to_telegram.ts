import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { CV_FILE_NAME } from "../lib/profile.js";

const inputSchema = z.object({
  kind: z.enum(["shortlist", "draft"]),
  text: z.string().min(1).max(3500),
  jobUrls: z.array(z.string().url()).min(1).max(6),
});

type SendInput = z.infer<typeof inputSchema>;

const cvPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../Tatanov Artem QA engineer.pdf",
);

function dryResult(input: SendInput) {
  return {
    delivered: false,
    submitted: false,
    reason: "dry_run",
    kind: input.kind,
    jobUrls: input.jobUrls,
  };
}

function telegramTarget(): { token: string; chatId: string } | null {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim() ?? "";
  const chatId = process.env.TELEGRAM_CHAT_ID?.trim() ?? "";
  if (!token || !chatId) return null;
  return { token, chatId };
}

async function telegramPost(token: string, method: string, body: BodyInit, json: boolean): Promise<number> {
  const headers = json ? { "content-type": "application/json" } : undefined;
  const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers,
    body,
    signal: AbortSignal.timeout(20_000),
  });
  return response.status;
}

export default defineTool({
  description:
    "Send a shortlist or an approved draft to Artem's own Telegram chat. Use kind shortlist for job links. Use kind draft only after prepare_application for that URL and only if he asked to receive the draft in Telegram. This never contacts an employer.",
  effect: "idempotent",
  inputSchema,
  dryRunResult: dryResult,
  async execute(input, ctx) {
    if (ctx.session.purpose === "eval") {
      return { delivered: false, submitted: false, reason: "eval", kind: input.kind };
    }

    if (input.kind === "draft") {
      if (input.jobUrls.length !== 1) {
        return { delivered: false, submitted: false, reason: "draft_needs_one_url" };
      }
      const prepared = await ctx.host.kv.get(`job-prepared:v1:${ctx.session.id}:${input.jobUrls[0]}`);
      if (prepared === undefined) {
        return { delivered: false, submitted: false, reason: "not_prepared" };
      }
      const already = await ctx.host.kv.get(`job-draft:v1:${ctx.session.id}:${input.jobUrls[0]}`);
      if (already !== undefined) {
        return { delivered: false, submitted: false, reason: "already_sent", kind: input.kind };
      }
    }

    const freshUrls: string[] = [];
    if (input.kind === "shortlist") {
      for (const url of input.jobUrls) {
        const seen = await ctx.host.kv.get(`job-notify:v1:${url}`);
        if (seen === undefined) freshUrls.push(url);
      }
      if (freshUrls.length === 0) {
        return { delivered: false, submitted: false, reason: "already_sent", kind: input.kind };
      }
    }

    const target = telegramTarget();
    if (!target) {
      return {
        delivered: false,
        submitted: false,
        reason: "telegram_not_configured",
        kind: input.kind,
      };
    }

    const messageStatus = await telegramPost(
      target.token,
      "sendMessage",
      JSON.stringify({
        chat_id: target.chatId,
        text: input.text,
        disable_web_page_preview: true,
      }),
      true,
    );
    if (messageStatus !== 200) {
      return { delivered: false, submitted: false, reason: "telegram_rejected", status: messageStatus };
    }

    let cvAttached = false;
    if (input.kind === "draft") {
      try {
        const bytes = await readFile(cvPath);
        const form = new FormData();
        form.set("chat_id", target.chatId);
        form.set("caption", "Резюме к черновику. Работодателю ничего не отправлено.");
        form.set("document", new Blob([bytes]), CV_FILE_NAME);
        const documentStatus = await telegramPost(target.token, "sendDocument", form, false);
        cvAttached = documentStatus === 200;
      } catch {
        cvAttached = false;
      }
    }

    const urlsToMark = input.kind === "shortlist" ? freshUrls : input.jobUrls;
    for (const url of urlsToMark) {
      const key = input.kind === "shortlist" ? `job-notify:v1:${url}` : `job-draft:v1:${ctx.session.id}:${url}`;
      try {
        await ctx.host.kv.put(key, { at: ctx.now().toISOString() });
      } catch {
        // The message is already in Telegram. A later duplicate is possible.
      }
    }

    return { delivered: true, submitted: false, kind: input.kind, cvAttached };
  },
});
