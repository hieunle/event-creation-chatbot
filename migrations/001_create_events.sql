CREATE TABLE IF NOT EXISTS events (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    date            DATE NOT NULL,
    time            TIME NOT NULL,
    description     TEXT,
    seat_types      JSONB NOT NULL,
    purchase_start  DATE NOT NULL,
    purchase_end    DATE NOT NULL,
    ticket_limit    INTEGER NOT NULL CHECK (ticket_limit > 0),
    venue_name      VARCHAR(255) NOT NULL,
    venue_address   VARCHAR(255) NOT NULL,
    capacity        INTEGER NOT NULL CHECK (capacity > 0),
    organizer_name  VARCHAR(255) NOT NULL,
    organizer_email VARCHAR(255) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    language        VARCHAR(50)  NOT NULL,
    is_recurring    BOOLEAN NOT NULL DEFAULT FALSE,
    recurrence_frequency VARCHAR(50),
    is_online       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT events_name_date_unique UNIQUE (name, date),
    CONSTRAINT events_purchase_window CHECK (purchase_end >= purchase_start),
    CONSTRAINT events_purchase_before_event CHECK (purchase_end <= date)
);

CREATE OR REPLACE FUNCTION events_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_updated_at ON events;
CREATE TRIGGER events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION events_set_updated_at();
