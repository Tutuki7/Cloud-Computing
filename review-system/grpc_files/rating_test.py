import asyncio
import grpc
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from grpc_files import rating_pb2, rating_pb2_grpc

load_dotenv()
GRPC_URL = os.getenv("GRPC_URL")

async def test_get_user_ratings(stub):
    req = rating_pb2.GetUserRatingsRequest(user_id=1)
    resp = await stub.GetUserRatings(req)

    print("\n=== GetUserRatings(user_id=1) ===")
    if not resp.ratings:
        print("No ratings found.")
    for r in resp.ratings:
        print(r)


async def test_get_movie_ratings(stub):
    req = rating_pb2.GetMovieRatingsRequest(movie_id=1)
    resp = await stub.GetMovieRatings(req)

    print("\n=== GetMovieRatings(movie_id=1) ===")
    if not resp.ratings:
        print("No ratings found.")
    for r in resp.ratings:
        print(r)


async def test_get_ratings(stub):
    req = rating_pb2.GetRatingsRequest(
        user_id=2,
        movie_id=1,
        min_rating=3.0,
        max_rating=5.0
    )
    resp = await stub.GetRatings(req)

    print("\n=== GetRatings(user_id=1, movie_id=1, min=3, max=5) ===")
    if not resp.ratings:
        print("No ratings found.")
    for r in resp.ratings:
        print(r)


async def main():
    target = GRPC_URL

    async with grpc.aio.insecure_channel(target) as channel:
        stub = rating_pb2_grpc.ReviewServiceStub(channel)

        while True:
            print("\n=== Review gRPC Test Menu ===")
            print("1. GetUserRatings (user_id=1)")
            print("2. GetMovieRatings (movie_id=1)")
            print("3. GetRatings (user_id=2, movie_id=1, min=3, max=5)")
            print("4. Exit")

            choice = input("Select an option: ").strip()

            if choice == "1":
                await test_get_user_ratings(stub)
            elif choice == "2":
                await test_get_movie_ratings(stub)
            elif choice == "3":
                await test_get_ratings(stub)
            elif choice == "4":
                print("Exiting test client.")
                break
            else:
                print("Invalid option.")


if __name__ == "__main__":
    asyncio.run(main())
