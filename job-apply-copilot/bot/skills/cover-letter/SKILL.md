---
description: Use when Artem has said yes to one specific vacancy and needs a cover letter plus his CV file. Do not use for a search.
---

# Cover letter

1. Call `prepare_application` with `userConfirmed: true` and the title, company, and URL he accepted.
2. Write the letter from `profile` and `letterRules` in the tool result. Do not add facts.
3. Answer him in Russian. Put the letter in one fenced block so he can copy it.
4. Name the CV file from `cvFile`. He attaches that file on the employer form.
5. Say that the application was not submitted.
6. Call `send_to_telegram` with `kind: "draft"` only when he asks to receive that draft in Telegram. One URL, the same URL you prepared.
