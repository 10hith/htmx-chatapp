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
4. **Write** the full itinerary to `/workspace/itinerary.md` (see format below).
5. **Remember**: save the user's stated preferences and chosen destinations to
   `/memories/preferences.md` so later turns can build on them.

## Itinerary format (`/workspace/itinerary.md`)

```
# {Destination} — {N}-day itinerary

## Day 1 — {theme}
- Morning: ...
- Afternoon: ...
- Evening: ...
- Eat: ...

## Day 2 — {theme}
...
```

## Conventions

- Prefer walkable clusters; note when a taxi/transit hop is needed.
- Always end your chat reply with a one-line summary, even though the full plan
  lives in the itinerary file.
- On a follow-up ("make day 2 more relaxed"), update the existing
  `/workspace/itinerary.md` rather than starting over, and update the todos.
