import asyncio
import grpc
from . import recommendation_pb2, recommendation_pb2_grpc
import os
from dotenv import load_dotenv

load_dotenv()
GRPC_URL = os.getenv("GRPC_URL")

async def test_create_preference(stub):
    req = recommendation_pb2.CreateUserPreferenceRequest(
        user_id=1,
        genre_id=5,
        preference_type="like"
    )
    resp = await stub.CreateUserPreference(req)

    print("\n=== CreateUserPreference (user_id=1, genre_id=5, preference_type=like) ===")
    print("Created:")
    print(f"  user_id: {resp.preference.user_id}")
    print(f"  genre_id: {resp.preference.genre_id}")
    print(f"  preference_type: {resp.preference.preference_type}")


async def test_get_preferences(stub):
    req = recommendation_pb2.GetUserPreferencesRequest(user_id=1)
    resp = await stub.GetUserPreferences(req)

    print("\n=== GetUserPreferences(user_id=1) ===")
    if not resp.preferences:
        print("No preferences found.")
    for p in resp.preferences:
        print(p)


async def test_delete_preference(stub):
    req = recommendation_pb2.DeleteUserPreferenceRequest(
        user_id=1,
        genre_id=5
    )
    resp = await stub.DeleteUserPreference(req)

    print("\n=== DeleteUserPreference (user_id=1, genre_id=5) ===")
    print("Deleted user preference:", resp.success)


async def test_add_reference_movie(stub):
    req = recommendation_pb2.AddReferenceMovieRequest(
        user_id=1,
        movie_id=10
    )
    resp = await stub.AddReferenceMovie(req)

    print("\n=== AddReferenceMovie (user_id=1, movie_id=10) ===")
    print("Added reference movie:")
    print(f"  user_id: {resp.reference_movie.user_id}")
    print(f"  movie_id: {resp.reference_movie.movie_id}")


async def test_get_reference_movies(stub):
    req = recommendation_pb2.GetReferenceMoviesRequest(user_id=1)
    resp = await stub.GetReferenceMovies(req)

    print("\n=== GetReferenceMovies(user_id=1) ===")
    if not resp.reference_movies:
        print("No reference movies found.")
    for r in resp.reference_movies:
        print(r)


async def test_delete_reference_movie(stub):
    req = recommendation_pb2.DeleteReferenceMovieRequest(
        user_id=1,
        movie_id=10
    )
    resp = await stub.DeleteReferenceMovie(req)

    print("\n=== DeleteReferenceMovie (user_id=1, movie_id=10) ===")
    print("Deleted reference movie:", resp.success)

async def test_get_recommendations(stub):
    req = recommendation_pb2.GetRecommendationsRequest(user_id=1)
    resp = await stub.GetRecommendations(req)

    print("\n=== GetRecommendations(user_id=1) ===")
    if not resp.recommendations:
        print("No recommendations found.")
    for r in resp.recommendations:
        print(r)    

async def main():
    async with grpc.aio.insecure_channel(GRPC_URL) as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)

        while True:
            print("\n=== Recommendation gRPC Test Menu ===")
            print("1. CreateUserPreference")
            print("2. GetUserPreferences")
            print("3. DeleteUserPreference")
            print("4. AddReferenceMovie")
            print("5. GetReferenceMovies")
            print("6. DeleteReferenceMovie")
            print("7. GetRecommendations")
            print("8. Exit")

            choice = input("Select an option: ").strip()

            if choice == "1":
                await test_create_preference(stub)
            elif choice == "2":
                await test_get_preferences(stub)
            elif choice == "3":
                await test_delete_preference(stub)
            elif choice == "4":
                await test_add_reference_movie(stub)
            elif choice == "5":
                await test_get_reference_movies(stub)
            elif choice == "6":
                await test_delete_reference_movie(stub)
            elif choice == "7":
                await test_get_recommendations(stub)
            elif choice == "8":
                print("Exiting test client.")
                break
            else:
                print("Invalid option.")


if __name__ == "__main__":
    asyncio.run(main())
