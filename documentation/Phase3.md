### Group
Joana Carrasqueira, 64414
Leonor Silva, 59811
Tiago Pereira, 55854
Tiago Pina, 66101

# Functional Requirements

## User Management
### FR1. User Registration
- System must allow new users to register with email, password, username and optional parameters (gender, age).
- Password must follow security requirements, such as:
    - at least 15 characters
    - at least one number
    - at least one uppercase letter
    - at least one special character
- Terms and conditions must be accepted.
- System must validate the email and username uniqueness.

### FR2. User Authentication
- System must authenticate users with OAuth2.0 or username/email and password.
- System must receive a unique authentication in the token upon OAuth2.0 login.
- If unique id doesn't exist in the system database, system must convert OAuth2.0 login into a profile compatible with the platform.
- System must invalidate OAuth2.0 token on logout.

### FR3. User Profile 
- Users must be able to update their profile (username, gender, age).
    -  Username must be unique.
- Users must be able to adjust their preferences.
- Users must be able to delete their account.

## Movie Catalog
### FR4. Movie Detail
- System must provide detailed view of a specific movie when requested by its unique identifier (movie ID), including: 
    - title
    - release date
    - list of genres
    - average rating (calculated from user reviews)
    - main cast (list of names)
    - director(s)
    - synopsis or description
    - runtime (duration in minutes)
    - parental rating (e.g. PG-13)
    - list of streaming platforms where the movie is currently available
- If the requested movie does not exist, the system must return an error message (e.g.  *"movie provided doesn't exist"*).

### FR5. Movie Search
- System must provide a text search endpoint for users to search for movies using keywords and/or filters.
- System must support filtering by:
    - genre
    - year range (from-to)
    - average rating
    - cast/director name
- Search results must support pagination and sorting by relevance, release date and rating.
- System must handle empty search queries gracefully (e.g., return popular or recently added movies).
- System must log search metrics (most searched terms, most used filters, etc.) for later analysis (can feed into the recommendation system).

### FR6. Movie List
- System must provide a list of movies with browsing options, including:
    - pagination
    - sorting by title, release date, rating, or popularity
    - filters by genre and year
- The response must include, for each movie: title, poster URL, year, list of genres, and average rating.
- User must be able to click on a movie to access its details.
- The default listing (without filters) must be sorted by descending release date (newest movies first).

### FR7. Movie CRUD
- System must allow only authorized administrators to create, read, update, and delete operations on movie entries.
- Movie creation/update must be validate:
    - title must be non-empty
    - release date must be a valid date (> 1887)
    - runtime > 0 (value in minutes)
    - at least one genre must be selected
    - poster URL must be a valid URL
    - parental rating must be one of the allowed values
- Movie deletion must be logical (soft delete):
    - Logically deleted movies do not appear in searches, listings, or details for regular users.
    - Reviews, ratings, and watchlists associated with deleted movies must be preserved for historical integrity, but not displayed.
- Any changes to movie data should be reflected across the system (e.g., in search, lists, details).

## Review System
### FR8. Rating CRUD
- Only authenticated users must be able to submit, edit, or delete their own reviews. 
- A review must contain a rating (integer from 1 to 5) and an optional text review (max 2000 characters).
- The system must enforce uniqueness: a user can have only one review per movie. If a new review is submitted for the same movie, the previous one is replaced (no version history).
- Editing is only allowed by the review author and must update the *updatedAt* timestamp.
- Deletion must be physical (hard delete) from the reviews table, but must preserve the movie and user records.
- Upon any rating change (create, update, delete), the system must trigger a recalculation of the movie's average rating.

### FR9. Ratings List
- System must allow retrieval of all ratings and reviews for a specific movie.
- The list must be:
    - paginated
    - sortable by date, rating, or helpfulness
    - optional filters: only with text, only without text
- For each rating, the system must display:
    - the user (username)
    - rating (1-5)
    - review text (if exists)
    - creation/update timestamp
- The system must not list reviews marked as fraudulent (highest level) for regular users.

### FR10. Recalculate Movie Rating
- System must maintain an accurate average rating for each movie based on all submitted ratings.
- Recalculation must be performed after each rating change (create, update, or delete) to prevent performance degradation.
- The updated average rating must be stored in the movie catalog database for quick retrieval.
- Only ratings not marked as fraudulent (highest level) should contribute to the average.

## Badges
### FR11. Badges CRUD
- System must allow administrators to create, read, update and delete badge definitions (e.g., “Explorer”, “Streak Master”).  
- Each badge definition must include at least: unique identifier, title, milestone rule and optional description.  
- System must validate that badge titles are unique across all badge definitions.  
- Deleting a badge definition must not remove historical records of badges already awarded to users, but must prevent the badge from being awarded in the future.  

### FR12. Award Badges
- System must automatically evaluate user activity (ratings, watchlists, viewing streaks, genre exploration, etc.) to determine when a user meets a badge milestone.  
- When a milestone is met, the system must award the corresponding badge to the user and store the award timestamp.  
- System must expose an operation to manually award or revoke badges for administrative purposes (e.g., correcting errors or running special campaigns).  
- Awarded badges must be visible (if user allows) in the user profile and retrievable via the badges API endpoints.  

### FR13. List User Badges
- System must allow retrieval of all badges awarded to a specific user, including badge details (title, milestone) and award date.  
- System must support pagination of user badges when a user has a large number of awarded badges.  
- System must support filtering user badges by badge type (e.g., exploration, streak) and by time window (e.g., badges earned in the last 30 days).  

## Watchlists
### FR14. Create Watchlist
- Users must be able to create a new watchlist by providing a title.
- Users should be able to add multiple movies to the watchlist after creation.
- The system must validate that the title is not empty.

### FR15. Edit Watchlist
- Users must add or remove movies from watchlists.
- Users must be able to rename a watchlist, as long as the new title does not duplicate another watchlist they own.
- The system must prevent adding the same movie twice.

### FR16. Delete Watchlist
- Users must be able to delete a watchlist they own.
- Deleting a watchlist must also remove all associated movie entries.
- The system must ensure that only the owner can delete their watchlist.

### FR17. Retrieve User Watchlists
- System must be able to retrieve all their watchlists and their contents.
- System must be able to retrieve a single watchlist by its ID.
- Users should be able to filter the contents of a watchlist by genre.

## Subscriptions
### FR18. Subscribe to Plan
- System must allow users to subscribe to a paid plan that unlocks premium features (e.g., advanced analytics, early access to new tools).  
- System must support at least one recurring plan (e.g., monthly) and store subscription start date, plan type and current status.  
- System must validate payment or external billing confirmation before activating a subscription.  

### FR19. Manage Subscription Plan
- Users must be able to view their current subscription status, including plan type, renewal date and payment status.  
- Users must be able to upgrade their free plan.
- Users must be able downgrade or cancel their paid subscription from within the platform.  
- System must ensure that subscription changes are reflected in access control to premium features.  

### FR20. Premium Access
- System must restrict access to selected premium features (such as detailed dashboards and advanced gamification insights) to users with an active premium subscription.  
- For each request to a premium endpoint, the system must validate the user’s subscription status through the Subscriptions service.  
- If the subscription is expired or cancelled, the system must deny access and return an appropriate error, suggesting re‑subscription.  

### FR21. Subscriptions CRUD 
- System must provide administrative operations to create, read, update and cancel subscriptions for support and correction purposes.  
- System must log all subscription lifecycle events (creation, renewal, cancellation, plan changes) for auditing and billing reconciliation.  

## Recommendation
### FR22. Initial Profile Recommendations
- New users must be able to select preferred genres and genres to avoid during the registration process.
- New users must be able to search and select 3 to 5 reference movies.
- The system must build a preference vector based on the user's explicit genre choices, reference titles, and similarities with other users.
- The system must generate tailored homepage shelves such as "Based on Your Genres", "Based on Your Favourite Titles" for the user's first session.

### FR23. Personalized Recommendations
- System must analyse a user’s rating history, preferred genres, and interactions to calculate personalized movie and series recommendations.
- System must order the recommended titles by year (ascending order).
- System must update recommendations as the user rates new titles or alters their watchlists.

### FR24. Genre Family Exploration
- System must group movies into "genre families" by analysing genre co-occurrence and overall user consumption patterns.
- System must calculate and categorize each user's consumption into highly explored and underexplored genre families.
- System must generate distinct discovery shelves for the user interface, such as "Comfort Zone" and "Explore Something New"

## Fraud Detection
### FR25. Detect Inconsistent Consumption
- System must continuously monitor user interactions (views, ratings, reviews) to detect anomalous patterns that may indicate fraud, compromised accounts, or bot activity.
- Anomaly detection should consider, among others:
    - sudden spikes in activity within a short period of pre-established account.
    - extreme ratings (e.g. 1 or 5) coming from new recent accounts or accounts with very little history.
- Detected anomalies must be persisted in a *fraud_alerts* table with: 
    - activated rule type
    - affected entity (ratingId, userId, movieId)
    - timestamp
    - severity (low, medium, high) defined by rule
- The system must support automatic action modes by severity:
    - high severity → automatically quarantine the rating
    - medium severity → send notification to admin
    - low severity → only log for analysis

### FR26. Review Fraud Treatment
- When a rating or review is identified as potentially fraudulent (e.g., part of review bombing), the system must quarantine it:
    - Exclude it from public averages, recommendations, and studio analytics.
    - Store quarantine metadata (reason, timestamp, user)
- Quarantined items must be reviewed by administrators, who can either restore them or permanently mark them as fraudulent.
- The system must maintain a log of all fraud detection events and actions taken.
- When an item is restored, the system must trigger a movie average recalculation event (because it now counts again).

## Studio Analytics
### FR27. Sentiment Analysis
- System must automatically process user text reviews using Natural Language Processing (NLP).
- System must classify each processed review into sentiment categories: positive, negative, or neutral.
- System must aggregate these sentiment metrics to calculate an overall sentiment score for each movie or series.

### FR28. Topic Extraction
- System must analyse reviews to extract frequently mentioned topics (e.g., plot, acting, special effects, pacing).
- System must generate automated summaries highlighting the most frequent strengths and weaknesses mentioned by the audience.

### FR29. User Cluster Analytics 
- System must group users into distinct segments (clusters) based on consumption history, preferred genres, and usage patterns.
- System must correlate and aggregate the extracted sentiments and topics specific to each user segment (e.g., showing how 'Casual Viewers' vs. 'Cinephiles' reacted to the same movie).


# Application Architecture
## Architecture Diagram
```mermaid
flowchart LR

subgraph ClientApps["Frontend (Web/Mobile)"]
    Client[User Interface]
end

subgraph Services
    UserManagement["User Management"]
    MovieCatalog["Movie Catalog"]
    ReviewSystem["Review System"]
    Badges["Badges"]
    Watchlists["Watchlists"]
    Subscriptions["Subscriptions"]
    Recommendations["Recommendations"]
    StudioAnalytics["Studio Analytics"]
    FraudDetection["Fraud Detection"]
end

subgraph Databases["Databases"]
    DB[(Main Database)]
    DBbackup[(Backup Database)]
end


Client -->|REST/HTTPS| APIGateway["API Gateway"] --> Services

Services --> |READ/WRITES| DB
DB <--> DBbackup
``` 

## Architecture Description 
- The system follows a modular, service‑oriented architecture designed for a cloud‑native environment.
- Each functional domain (movies, ratings, watchlists, analytics, etc.) is implemented as an independent backend service.
- All services are exposed through a unified API Gateway, which acts as the single public entry point.
- This architecture directly reflects the functional requirements defined earlier and supports future deployment on Kubernetes.

### API Gateway
The API Gateway is responsible for:
- Routing incoming REST requests to the appropriate backend service
- Enforcing authentication (OAuth2.0)
- Providing a single stable endpoint for all clients
- Applying request validation and basic rate limiting

This ensures that clients interact with a single, consistent API, regardless of internal service structure.
### Microservices
- Each service corresponds to a functional domain and maps directly to the OpenAPI specification and functional requirements.

| Microservice     | Description                                                             |
| ---------------- | ----------------------------------------------------------------------- |
| User Management  | Registration, authentication, profile updates, OAuth2 integration       |
| Movie Catalog    | Movie CRUD, search, filtering, metadata retrieval                       |
| Review System    | Ratings, reviews and average scores recalculation                       |
| Badges           | Badge definitions, awarding logic, user achievements                    |
| Watchlists       | CRUD watchlists, add/remove movies, filtering                           |
| Subscriptions    | Subscription lifecycle, plan management, premium access control         |
| Recomendation    | Hybrid recommendations, genre families and personalised recommendations |
| Fraud Detection  | Anomaly detection, review bombing mitigation, quarantine logic          |
| Studio Analytics | NLP sentiment analysis, topic extraction, user cluster analytics        |

### Databases
#### Main Database (PostgreSQL or something else)
- responsible for storing data such as users, movies, ratings, watchlists, badges, subscriptions.
- supports high‑frequency reads/writes and ensures data consistency.
#### Backup Databases
- responsible for performing periodic backups to the main database
- ensuring redundancy of the main database for disaster recovery

### Protocols
- **REST/HTTPS** for all client–server communication
- **SQL** for databases 
- **REST** for backend services 
