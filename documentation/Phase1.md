### Group
Joana Carrasqueira, 64414
Leonor Silva, 59811
Tiago Pereira, 55854
Tiago Pina, 66101

# Project description
**Description:** a platform which offers unified catalog of movies, a public review system, and a personal watchlist to keep users organize all the titles they interact with. On top of this, the platform includes a recommendation system that suggests future watches based on each user's history.

**Objective:** build and deploy cloud-native analytics and recommendation platform built on movie datasets.

## Datasets 
### Main Datasets : MovieLens 25M
- **URL:** https://grouplens.org/datasets/movielens/25m/
- **Topic:** ratings and tag applications applied to 62,000 movies by 162,000 users.
- **Size:** 1,07 GB
- **Format:** csv
- **Date of release:** November 21, 2019

### Auxiliary datasets
#### Netflix Movies and TV Shows
- **URL:** https://www.kaggle.com/datasets/shivamb/netflix-shows
- **Topic:** listings of all the movies and tv shows available on Netflix, along with details such as cast, directors, ratings, release year, duration, etc.
- **Format:** csv
- **Date of release:** 2024
- **Size:** 3,4 MB

#### IMDb Non-Commercial Datasets
- **URL:** https://datasets.imdbws.com/
- **Topic:** metadata about movies, TV shows, episodes, and people.
- **Format:** tsv (UTF-8)
- **Date of release:** March 18, 2024 (updates daily)

| filename                | size    |
| ----------------------- | ------- |
| title.basics.tsv.gz     | ~1 GB   |
| title.ratings.tsv.gz    | 27,3 MB |
| name.basics.tsv.gz      | 892 MB  |
| title.principals.tsv.gz | 4,08 GB |

## Business Capabilities
### BC1. Subscriptions System
- **Description:** A subscription plan with two tiers (free or premium), would provide direct revenue with the higher tier option. Users with premium plan would have access to functionalities such as advanced statistics for watching habits and beta access to new functionalities.
- **Source of income:** Monthly or yearly subscriptions (premium).

### BC2. Advertising in Search
- **Description:** Inclusion of adds in recommendation system, where studios or streaming services can promote their releases in specific segments (search engine) based on user's history and preferences. 
- **Source of income:** Advertising fees from studios, streaming services, or third-party brands paying to promote their titles or content segments to targeted users.

###  BC3. Engagement Badges System
- **Description:** Exclusive badges on completing milestones of usage of the platform, such ass certain amount of ratings made, exploring new genres of content, and creating watchlists.
- **Source of income:** Increase in retention and time spent, reinforcing the value of other capabilities (advertising, premium features). Potential sale of this module as a white-label solution to other content platforms.

###  BC4. Analytics to Studios and Producers
- **Description:** Advanced analytics dashboard providing insights into genre trends (average popularity over time), actor performance (average revenue per film, average rating, number of appearances), and the correlation between budget and revenue. Enables data-driven decision-making for content investment, casting, and distribution strategies.
- **Source of income:** Premium subscription model for studios and production companies. Customized reports and data exports.

###  BC5. Smart Intelligent Review System
- **Description:** AI-powered system that performs automatic sentiment analysis (classifying reviews as positive, negative, or neutral), generates summaries of the most frequent strengths and weaknesses mentioned in reviews, and identifies recurring topics using techniques such as LDA. Helps both users and industry professionals quickly extract meaningful insights from large volumes of text.
- **Source of income:** Increased user engagement and retention (boosting advertising and premium value). Premium access to advanced review insights.

## Use Cases
### UC1. Hybrid Initial Profile Creation (Genres + Reference Movies)
- **Actor:**  Newly registered user.
- **Problem:** A new user wants relevant recommendations immediately but has no viewing history on the platform.
- **Description:**
	1.  During registration, the user selects preferred genres and genres to avoid through a simple checklist interface.
	2. Optionally, the user searches for and selects 3–5 movies they consider personal references (*“I love this movie”*).
	3. The system builds a preference vector that combines explicit genre information with inferred patterns derived from the selected reference titles and from similar users.
	4. In the first session after registration, the user receives a homepage organized into distinct shelves: *“Based on Your Genres”*, *“Based on Your Favourite Titles”*, and, if applicable, filtered by the streaming platforms the user has indicated they own.
- **Expected outcome:** Initial recommendations with strong accuracy and diversity, reducing the cold-start problem and increasing the likelihood that the user finds appealing content during their first interaction with the platform.

### UC2. Guided Exploration by Genre Families
- **Actor:**  Registered user.
- **Problem:** The user tends to remain stuck in the same types of content and struggles to discover interesting variations within and around the genres they enjoy.
- **Description:**
	1. The system analyses the database of movies and identifies *“genre families”* based on genre co-occurrence and consumption patterns (e.g., action + sci-fi + superheroes; drama + biography; horror + psychological thriller).
	2. For each user, it calculates which genre families are highly explored (high consumption and strong ratings) and which related families remain underexplored, also considering the behaviour of similar users.
	3. The interface presents shelves such as *“Comfort Zone"*, *“More of the Same, but Different”*, and *“Explore Something New”*, each containing recommendations ranked by the probability of user satisfaction and filtered according to the streaming platforms the user owns.
- **Expected outcome:** A discovery experience that gently encourages users to step slightly outside their comfort zone in a controlled way, increasing content diversity without sacrificing relevance.

### UC3. Inconsistent Consumption Flow Detection System
- **Actor:**  Platform (security team, data science team).
- **Problem:** Sudden changes and atypical consumption or rating patterns may indicate fraud, compromised accounts, or noise that harms the quality of recommendations and the reliability of metrics presented to studios.
- **Description:** 
	1. For each user, the system maintains a routine profile that includes typical viewing times, most-used devices, rating distribution, and most frequent genres.
	2. Anomaly detection algorithms continuously monitor new interactions (views, ratings, reviews) to identify inconsistent flows, such as sudden spikes in completely different genres, sequences of extreme ratings within a short period, or usage from unusual devices or locations.
	3. The system distinguishes between potentially malicious patterns (e.g., coordinated review bombing across many new users) and genuine shifts in taste (gradual and consistent changes over time), applying adaptive rules and models.
	4. Depending on the type of anomaly, it takes actions such as quarantining certain interactions so they do not affect public metrics, requesting additional user verification, or adjusting the weight of certain genres in the profile to reflect a real evolution of interests.
- **Expected outcome:** Greater robustness of recommendations and internal statistics, protection against fraud, and the ability to track the natural evolution of user preferences without overreacting to isolated behaviour.

### UC4. Sentiment and Topic Dashboard by User Segment
- **Actor:**  Studios, production companies, marketing teams, and content strategy teams.
- **Problem:** Textual reviews are numerous and heterogeneous, making it difficult to quickly understand how different audience segments react to a movie or series and which specific aspects generate praise or criticism.
- **Description:**
	1. The system applies Natural Language Processing techniques to automatically classify each review as positive, negative, or neutral, and to extract frequent topics (e.g., plot, acting, pacing, special effects, cinematography).
	2. In parallel, it uses user clusters obtained through clustering techniques based on consumption history, preferred genres, and usage patterns, forming segments such as *“Blockbuster Lovers"*, *“Classic Cinephiles”*, *“Casual Viewers”*,  etc.
	3. For each movie or series, the system aggregates sentiment metrics by segment (e.g., “Classic Cinephiles – 80% positive about the plot; Blockbuster Lovers – 90% positive about special effects; Casual Viewers – 50% neutral overall”) and highlights the most frequently mentioned topics within each group.
	4. These results are presented in an interactive dashboard that allows studios to filter by segment, topic, and time window to track how audience reception evolves over time.
- **Expected outcome:** A structured view of audience reception, enabling more informed decisions regarding marketing strategies, trailers, sequels, creative adjustments, and campaign targeting.

### UC5. Review Fraud Detection
- **Actor:** Platform integrity system. 
- **Problem:** Protecting the integrity of public movie averages from "review bombing." 
- **Description:**
	1. The system uses anomaly detection algorithms (review bombing) to monitor the continuous flow of ratings. The process occurs in real time. 
	2. When it identifies statistically abnormal peaks of extreme ratings from recent or suspicious accounts, the system automatically quarantines these ratings. 
- **Expected outcome:** Secured and credible platform public averages.

### UC6. Gamification with Quests, Streaks, and Genre Exploration
- **Actor:** Registered User
- **Problem:** Even with good recommendations, some users lose motivation, fall into repetitive viewing habits, or stop interacting with the platform (e.g., stop rating, writing reviews, or exploring new content).
- **Description:**
	1. The system introduces gamification mechanics inspired by apps that use streaks, quests, and milestones to increase retention, such as learning platforms and habit-tracking apps.
	2. Daily, weekly, or seasonal missions are defined, for example:
	  - *“Maintain a 3-day streak by watching at least 1 episode/movie per day”*
	  - *“Watch 2 movies from a genre you rarely explore”*
	  - *“Complete a trilogy or an entire season”*
	  - *“Rate 5 titles you recently watched”*
	3. The system automatically tracks progress using viewing history and ratings, adjusting quest difficulty based on the user’s actual behaviour to ensure goals are challenging yet achievable.
	4. Rewards, in the initial phase, focus on intrinsic motivation and platform features:
	   - Profile badges
	   - Extra statistics (genre exploration maps, streak history)
	   - Minor interface unlocks
	   - Early access to some premium analytics features
- **Expected outcome:** Increased user retention, higher volume of user data (ratings, reviews, consumption diversity), and encouragement to explore new genres, which in turn improves the recommendation engine and enriches the analytics offered to studios.

### UC7. Personalized Recommendations for Registered User
- **Actor:** Registered user.
- **Problem:** The user has difficulty finding movies and series that match their personal tastes.
- **Description:** 
    1. The system analyses the user’s rating history, preferred genres, similar movies/series rated by like-minded users, content popularity, and metadata. 
    2. Based on this data, it generates a personalized list of recommendations.
- **Expected Outcome:** A list of movies/series ordered by relevance.

### UC8. Search Movies
- **Actor:** User.
- **Problem:** The user wants to find movies that match specific criteria but may struggle to locate them quickly.
- **Description:** 
	   1. The user enters search terms or applies filters such as genre, year range, or minimum rating. 
	   2. The system returns paginated results showing titles that match the search query.
	   3. The user can browse through pages of results and select a title for more details if desired.
- **Expected outcome:** The user receives a clear, paginated list of movies relevant to their search criteria, improving content discovery and efficiency in finding desired titles.

### UC9. View Movie Details
- **Actor:** User
- **Problem:** The user wants to access all relevant information about a specific movie to decide whether to watch it.
- **Description:**
    1. The user selects or requests a title by its unique ID.
    2. The system retrieves and displays detailed information about the title, including:
       - Title name
       - Release date
       - Number of seasons (if applicable)
       - Genres
       - Average rating
       - Main cast
       - Description or synopsis (if available)
    3. The information is presented in a structured format that allows the user to quickly scan key details and make informed decisions.
- **Expected outcome:** The user obtains complete and accurate details for any selected title, improving content discovery and supporting informed viewing choices.

### UC10. Rate and Review a Title
- **Actor:** Authenticated user
- **Problem:** The user wants to share their opinion about a movie and contribute to the platform’s public ratings and reviews.
- **Description:**
	1. The user submits a rating (from 1 to 10) and an optional text review for a specific title.
	2. The system stores the rating and review in the platform database.
	3. The system recalculates the title’s average rating in real time and updates it accordingly.
	4. The review is displayed publicly, contributing to the overall rating and helping other users make informed viewing decisions.
- **Expected outcome:** The user’s rating and review are saved and reflected in the platform’s average score, enriching the community-driven evaluation system and improving recommendations.

### UC11. Manage Personal Watchlist
- **Actor:** Registered user
- **Problem:** The user wants to organize and track their viewing plans but needs a structured way to manage movies of interest.
- **Description:**
	1. The user adds or removes titles from personal lists, such as *“Watchlist”*, *“Currently Watching”*, or *“Finished”*.
	2. The system persists these lists in the user’s profile, ensuring data is saved across sessions and devices.
	3. The system allows retrieval and filtering of the lists by genre.
	4. The user can easily track their progress and manage their planned or completed viewing.
- **Expected outcome:** Users have an organized, personalized watchlist that helps them plan and track their content consumption efficiently, enhancing engagement and platform loyalty.

### UC12. Login / Authenticate User
- **Actor:** Registered user
- **Problem:** The user wants to access their personalized account but needs to verify their identity securely.
- **Description:**
	1. The user enters login credentials, typically email/username and password.
	2. The system validates the credentials against stored account data.
	3. If credentials are correct, the system grants access to the user’s account and personalized features.
	4. If credentials are incorrect, the system notifies the user and may offer password recovery options.
- **Expected outcome:** The user successfully authenticates and accesses their account, enabling use of personalized recommendations, watchlists, ratings, and other platform features.
