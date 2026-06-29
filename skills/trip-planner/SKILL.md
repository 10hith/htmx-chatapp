---
name: trip-planner
description: Structured approach to planning multi-day trips — clarify constraints, build a day-by-day itinerary, track planning steps as todos, and save preferences to memory.
---

# Trip Planner

A repeatable method for turning a vague trip request into a concrete, day-by-day
plan. Use it whenever the user asks to plan, refine, or adjust a trip.

## Workflow (keep a todo list of these stages with `write_todos`)

1. **Clarify** the essentials if missing: destination(s), number of days, dates or
   season, travel style (budget / mid / luxury), and any must-dos. If the user
   already gave enough, state your assumptions instead of asking.
2. **Outline** the trip at a high level (themes per day, rough geography so each
   day clusters nearby sights — minimise backtracking).
3. **Detail** each day: morning / afternoon / evening with 2–4 activities, a food
   suggestion, and approximate travel between stops.
4. **Write** the full itinerary as styled HTML to `/workspace/itinerary.html`.
5. **Remember**: save the user's stated preferences and chosen destinations to
   `/memories/preferences.md` so later turns can build on them.
6. **Reply** in chat with exactly one plain-text sentence, then a fenced ```html
   block containing a compact rich summary for the chat bubble.

## HTML format (`/workspace/itinerary.html` and chat card)

Choose the HTML form that best fits the content rather than forcing one template:

- Use `table` for budgets, schedules, tradeoffs, and comparisons.
- Use DaisyUI `stats` / `stat` blocks for headline numbers.
- Use DaisyUI `alert` blocks for warnings, booking tips, weather notes, or caveats.
- Use `ul` / `ol` lists, DaisyUI `steps`, or timeline-like lists for sequences.
- Use cards, headings, sections, and badges for tidy summaries.
- Use `details` / `summary` for collapsible optional details.

Hard rules:

- Use only structural/text/table/details tags and the `class` attribute.
- Tailwind and DaisyUI classes are welcome.
- Use emoji glyphs for all icons.
- Never use `<script>`, `<style>`, `<img>`, `<a>`, links, `<svg>`, inline event
  handlers, or `style=`.
- Keep the chat card compact; put the complete day-by-day plan in
  `/workspace/itinerary.html`.

Example shapes:

```html
<div class="alert alert-info"><span>🚆 This plan clusters each day by neighborhood to reduce transit time.</span></div>
```

```html
<table class="table table-zebra"><thead><tr><th>Day</th><th>Theme</th><th>Base area</th></tr></thead><tbody><tr><td>1</td><td>Temples and old lanes</td><td>Higashiyama</td></tr></tbody></table>
```

```html
<details class="collapse bg-base-200"><summary class="collapse-title">Rainy-day swap</summary><div class="collapse-content"><p>Move the garden walk to morning and reserve an indoor museum for the afternoon.</p></div></details>
```

## Conventions

- Prefer walkable clusters; note when a taxi/transit hop is needed.
- Always include a one-line plain-text summary before the fenced chat HTML block,
  even though the full plan lives in the itinerary file.
- On a follow-up ("make day 2 more relaxed"), update the existing
  `/workspace/itinerary.html` rather than starting over, and update the todos.
