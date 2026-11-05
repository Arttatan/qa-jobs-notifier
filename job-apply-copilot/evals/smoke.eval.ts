import { defineEval } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description: "A vacancy search returns links and does not prepare or send an application.",
  async test(t) {
    await t.send("Find remote QA vacancies and show the links. Do not write a cover letter.");
    t.succeeded();
    t.calledTool("search_jobs");
    t.notCalledTool("prepare_application");
    t.notCalledTool("send_to_telegram");
  },
});
