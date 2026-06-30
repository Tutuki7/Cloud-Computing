
DROP TABLE IF EXISTS subscriptions CASCADE;

CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP
);

