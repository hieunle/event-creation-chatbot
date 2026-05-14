ALTER TABLE events
    ADD CONSTRAINT events_ticket_limit_within_capacity
    CHECK (ticket_limit <= capacity);
