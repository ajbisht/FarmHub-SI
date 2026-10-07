# OPERATING RULES — Autonomous Farm Irrigation POC

These rules apply to every session in this project. They override anything else.
The full project description is in `BRIEF.md` in this folder. Read it before doing anything.

1. **Do NOT create, edit, or delete any file, run any command, or install anything** until I reply with the exact words `APPROVED: <stage name>`.
2. **Your first and only job at the start is Stage 0: ask me questions.** Do not draft a plan, do not scaffold a repo, do not write code.
3. Ask in **batches of at most 8 numbered questions**. For every question, give your **recommended default** so I can answer "defaults" or reply inline (e.g. `3: yes, 5: use Flask`).
4. `BRIEF.md` Section 7 lists the questions I already know are open. Ask those, plus anything else you think is unclear or risky. Do not assume answers.
5. After I answer, produce an **Implementation Plan artifact** and **wait for my review**. Do not proceed until I approve it.
6. Work in **small stages**. After each stage: stop, show what you did, show how to test it, and wait for my "APPROVED: next stage".
7. **I am a DevOps architect, not a developer, and I am new to AI agents, sensors and embedded work.** Explain in simple words, give exact copy-paste commands, and say what each step does.
8. **Scope discipline:** this is a small proof of concept. Anything beyond `BRIEF.md` goes under a heading "Proposed — not approved". Never add it silently.
9. If anything in `BRIEF.md` looks wrong, contradictory, or unsafe, **tell me and ask** instead of silently fixing it.
10. **Secrets:** never put API keys in code or in chat. Use a `.env` file and a `.env.example` with placeholders. Make sure `.env` is git-ignored.
11. You cannot touch the hardware. I do all physical steps (wiring, flashing, plumbing). Give me checklists for those.
