from config import vertexai_client, subscription_path, subscriber, SessionLocal, ReviewSentiment, RatingTopic, Topic, MODEL
import json

# llm review processing
def process_review(review_text):
    prompt = f"""
    Analyze the following movie review: "{review_text}"
    Extract the overall sentiment (choose exactly one: "positive", "negative", or "neutral") 
    and extract up to 5 main topics discussed (e.g., "acting", "plot", "special effects").
    Format strictly as JSON: {{"sentiment": "positive", "topics": ["topic1", "topic2"]}}
    """
    
    response = vertexai_client.models.generate_content(model=MODEL, contents=prompt)
    clean_text = response.text.replace('```json', '').replace('```', '').strip()
    result = json.loads(clean_text)
        
    sentiment = result.get('sentiment', 'neutral').lower()
    topics_res = result.get('topics', [])[:5]
    topics = [t.lower().strip() for t in topics_res] 

    return sentiment, topics

# updates db based on processed review
def save_review(rating_id, sentiment: str, topics: list[str]):
    db = SessionLocal()
    try:
        # deletes older review sentiment and topics 
        db.query(ReviewSentiment).filter(ReviewSentiment.rating_id == rating_id).delete()
        db.query(RatingTopic).filter(RatingTopic.rating_id == rating_id).delete()
        
        new_sentiment = ReviewSentiment(rating_id=rating_id, sentiment_label=sentiment)
        db.add(new_sentiment)

        for name in topics:
            topic = db.query(Topic).filter(Topic.name == name).first() # check if it exists

            if not topic: # creates a topic if it doesn't exist
                topic = Topic(name=name)
                db.add(topic)
                db.flush()
            
            # links the topic to the rating
            rating_topic = RatingTopic(rating_id=rating_id, topic_id=topic.topic_id)
            db.add(rating_topic)

        db.commit()
        print(f"Successfully saved analysis for rating_id {rating_id}")

    except Exception as db_e:
        db.rollback()
        print(f"Database error: {db_e}")
    finally:
        db.close()

# pub/sub callback
def callback(message):
    try:
        data = json.loads(message.data.decode("utf-8"))
        rating_id = data['rating_id']
        review_text = data['review']
        
        print(f"Processing rating_id: {rating_id}")
        sentiment, topics = process_review(review_text)
        save_review(rating_id, sentiment, topics)

        message.ack()
    except Exception as e:
        print(f"Failed to process message: {e}")
        message.nack()

# starts connection to pub/sub
print(f"Listening for messages on {subscription_path}...")
streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)

with subscriber:
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()