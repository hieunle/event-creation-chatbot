# Sample conversation transcripts

Two illustrative runs. Both follow the spec's response format:
**acknowledgement → clarification → one actionable next sentence**, and end
each turn with a single concrete question.

---

## 1. Successful end-to-end flow

```
User: I want to create an event.
AI  [scenario=missing_field]:
  Great! What's the name of your event?

User: Kyoto Jazz Night.
AI  [scenario=missing_field]:
  Got it — "Kyoto Jazz Night". When will it take place? (YYYY-MM-DD)

User: March 10, 2026 at 7pm.
AI  [scenario=missing_field]:
  Thank you. You mentioned 2026-03-10 at 19:00. Could you describe the event
  briefly?

User: A live jazz performance in Kyoto.
AI  [scenario=missing_field]:
  Understood. What seat types and prices do you offer? (e.g., VIP: 10000,
  Regular: 5000)

User: VIP for 10000 yen, Regular for 5000.
AI  [scenario=missing_field]:
  Recorded VIP at 10000 and Regular at 5000. How many tickets can one
  person buy?

User: 4 tickets per person.
AI  [scenario=missing_field]:
  Got it. When does ticket purchase open and close?

User: Sales open Jan 1, 2026 and close March 9, 2026.
AI  [scenario=missing_field]:
  Thanks. Purchase window: 2026-01-01 to 2026-03-09. What is the venue name?

User: Kyoto Concert Hall.
AI  [scenario=missing_field]:
  Got it. What is the venue address?

User: 123 Sakyo-ku, Kyoto.
AI  [scenario=missing_field]:
  Thank you. What's the venue capacity?

User: 1000 seats.
AI  [scenario=missing_field]:
  Recorded. Who is organizing this event?

User: Fenix Entertainment, contact info@fenix.co.jp.
AI  [scenario=missing_field]:
  Got it — Fenix Entertainment (info@fenix.co.jp). What category fits this
  event? (e.g., Concert, Festival)

User: Concert. In Japanese. It's offline and a one-off, not recurring.
AI  [scenario=confirmation]:
  Perfect. Confirming:
    • Kyoto Jazz Night — 2026-03-10 19:00
    • Kyoto Concert Hall, 123 Sakyo-ku, Kyoto (capacity 1000)
    • VIP: 10000, Regular: 5000 — up to 4 per person
    • Sales 2026-01-01 → 2026-03-09
    • Concert, Japanese, offline, one-off
    • Organized by Fenix Entertainment (info@fenix.co.jp)
  Shall I save this event?

User: Yes.
AI  [scenario=success_save]:
  ✅ Event "Kyoto Jazz Night" registered successfully (event_id=1).
  Would you like to create another event?
```

JSON envelope for the final turn:

```json
{
  "role": "assistant",
  "scenario": "success_save",
  "message": "✅ Event \"Kyoto Jazz Night\" registered successfully (event_id=1). Would you like to create another event?"
}
```

---

## 2. Error-handling: invalid input + duplicate + revision

```
User: Make an event called Tokyo Anime Expo on March 32, 2026.
AI  [scenario=invalid_input]:
  Got the name — "Tokyo Anime Expo". The date "March 32" isn't valid.
  Could you provide it in YYYY-MM-DD format?

User: Sorry, March 22, 2026.
AI  [scenario=missing_field]:
  Thank you — 2026-03-22 recorded. What time does it start? (HH:MM, 24-hour)

User: 10am.
AI  [scenario=missing_field]:
  Got it — 10:00. What seat types and prices?

User: General 3000 yen.
AI  [scenario=missing_field]:
  Recorded General at 3000. How many tickets can one person buy?

User: Five.
AI  [scenario=missing_field]:
  Got it — 5 tickets per person. When does ticket purchase open and close?

User: From Feb 1 to March 21, 2026.
AI  [scenario=missing_field]:
  Thanks. Sales window 2026-02-01 → 2026-03-21. What's the venue?

User: Tokyo Big Sight, 3-11-1 Ariake, Koto-ku. Capacity 5000.
AI  [scenario=missing_field]:
  Got Tokyo Big Sight at 3-11-1 Ariake, Koto-ku, capacity 5000. Who's the
  organizer and what's their contact email?

User: organizer@bad@email
AI  [scenario=invalid_input]:
  That email doesn't look valid (must be like name@domain.com). Could you
  provide a valid organizer email?

User: organizer@anime-expo.jp, organizer name Anime Expo Inc.
AI  [scenario=missing_field]:
  Thank you. Recorded Anime Expo Inc. (organizer@anime-expo.jp). What
  category? (e.g., Convention, Festival)

User: Convention, in Japanese, offline, one-off.
AI  [scenario=confirmation]:
  Confirming:
    • Tokyo Anime Expo — 2026-03-22 10:00
    • Tokyo Big Sight, 3-11-1 Ariake, Koto-ku (capacity 5000)
    • General: 3000 — up to 5 per person
    • Sales 2026-02-01 → 2026-03-21
    • Convention, Japanese, offline, one-off
    • Anime Expo Inc. (organizer@anime-expo.jp)
  Shall I save this event?

User: Actually, change the date to March 23.
AI  [scenario=update_previous_field]:
  Got it. Updated the event date from 2026-03-22 to 2026-03-23. Shall I
  save this event?

User: Yes.
AI  [scenario=success_save]:
  ✅ Event "Tokyo Anime Expo" registered successfully (event_id=2). Want
  to create another?

User: Yes, another Tokyo Anime Expo on March 23.
AI  [scenario=invalid_input]:
  An event named "Tokyo Anime Expo" on 2026-03-23 already exists. Would
  you like to use a different name or date?
```

The final turn shows the duplicate-detection path: the
`update_event_draft` tool ran the repository's `find_duplicate` check
once both name and date were filled, returned a `duplicate` status on the
`name` field, and the LLM mapped that to `invalid_input`.

---

## 3. Lookup — querying past events

Two short single-turn flows. Both use `scenario=lookup` per the rubric in
`app/agent/prompts.py:48`.

**Structured query** (date / category / "latest" / counts):

```
User: What's the most recent event I created?
AI  [scenario=lookup]:
  Got it. The most recent event is "Tokyo Anime Expo" on 2026-03-23 at
  Tokyo Big Sight. Want to create another, or look at something else?
```

Internally the agent called `query_events({latest: true, limit: 1})`.

**Semantic search** (fuzzy / by topic):

```
User: Find my jazz events.
AI  [scenario=lookup]:
  Found one match: "Kyoto Jazz Night" on 2026-03-10 at Kyoto Concert Hall.
  Want details on it, or to create another?
```

Internally the agent called `search_events({query: "jazz", k: 5})`, which
hits the ChromaDB vector store rather than SQL.

---

## 4. Small talk

A greeting where no field is being collected — agent does not advance the
draft, and `scenario=small_talk` per `app/agent/prompts.py:49`.

```
User: hey, thanks for the help earlier!
AI  [scenario=small_talk]:
  You're welcome! Glad it worked out. Let me know when you want to create
  another event.
```

The agent may still call `update_event_draft({})` to confirm there's
nothing to extract, but no fields change and no save tools run.
