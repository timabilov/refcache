#!/bin/bash
set -e

# Start Redis and Redis UI with docker-compose
echo "Starting Redis and"
docker-compose up -d

# Wait for Redis to be ready
echo "Waiting for Redis to be ready..."
until docker-compose exec -T redis redis-cli ping | grep -q PONG
do
  echo "Redis not ready yet, retrying..."
  sleep 1
done


echo "Running tests..."

# Run the tests
if [ -z "$1" ]; then
  # Run all tests if no specific test is provided
  python -m pytest
else
  # Run specific test if provided
  python -m pytest "$@"
fi

# Optional: Stop Redis after tests
# Uncomment the following line if you want Redis to stop after tests
# docker-compose down

docker-compose down