# Event Creation Chatbot

A backend system that helps users create event records through a conversational interface. The chatbot guides users through collecting all required event data, validates it, and persists complete events to PostgreSQL.

## Language

**Event**:
A record describing a real-world happening (concert, conference, etc.) saved to the `events` table. Has a name, date/time, venue, organizer, ticket configuration, and metadata.
_Avoid_: Booking, reservation

**EventDraft**:
A partially-completed Event held in conversation state while the user is still providing information. Becomes an Event once all required fields are filled and the user confirms the save.
_Avoid_: Pending event, partial event, in-progress event

**Session**:
One chat thread aimed at creating one Event. Identified by a `thread_id`. State (messages + draft) persists across HTTP requests via the LangGraph checkpointer.
_Avoid_: Conversation, thread (informal synonyms only)

**Seat type**:
A category of seating offered for an Event (e.g., "VIP", "Regular", "Standing"), each with its own ticket price. Stored as a JSONB map `{seat_type: price}` on the Event.
_Avoid_: Ticket type, seating tier

**Purchase period**:
The time window during which tickets for an Event can be bought, defined by `purchase_start` and `purchase_end`. Must end on or before the Event date.
_Avoid_: Sale window, ticket window

**Scenario**:
The category label attached to every chatbot response, drawn from a fixed Literal set: `missing_field | invalid_input | confirmation | success_save | error_db | update_previous_field | lookup | small_talk`. Determines the UI badge and signals what the user can do next. The two non-collection scenarios:
- `lookup` — the turn answered a question about past events via `query_events` or `search_events`.
- `small_talk` — greeting, thanks, or off-topic chatter where no field was being collected.

_Avoid_: Intent, response type, action

**Confirmation step**:
The point in a Session where all EventDraft fields are filled and the chatbot summarizes them, asking the user to approve the save before insertion. The save only happens after explicit user confirmation.
_Avoid_: Final step, review

## Relationships

- A **Session** progressively builds exactly one **EventDraft**.
- An **EventDraft** becomes an **Event** when complete and confirmed at the **Confirmation step**.
- An **Event** has one or more **Seat types**, each with a price.
- An **Event** has one **Purchase period** governing when tickets can be bought.
- Every chatbot response carries exactly one **Scenario**.

## Example dialogue

> **Dev:** "When the user says 'change the date to March 12th,' is that part of collection or the **Confirmation step**?"
> **Domain expert:** "Either. They might revise during collection, or they might revise after seeing the summary at the **Confirmation step** before approving the save. In both cases the **Scenario** is `update_previous_field`."

## Flagged ambiguities

- "Event" was used for both the saved row and the in-progress data — resolved: in-progress = **EventDraft**, saved = **Event**.
- "Scenario" vs. "intent" — resolved: we use **Scenario** consistently. The agent has no separate intent-classification step; **Scenario** is the *output* category attached to each response, not an input the agent classifies.
