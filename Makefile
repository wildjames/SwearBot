.PHONY: install-dev lint run clean unpack

# Installs both normal and dev dependencies
# Not needed for running as uv run handles deps itself
install-dev:
	uv sync

lint:
	uv run ruff check .

build:
	uv build

run:
	uv run balaambot

unpack:
	unzip -u sounds.zip

clean:
	@echo "Cleaning up..."
	# Remove Python bytecode and __pycache__ directories
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	# Remove Ruff cache
	rm -rf .ruff_cache
	# Remove build artifacts
	rm -rf build/ dist/ *.egg-info
	# Remove sounds directory if it exists
	rm -rf sounds/
	rm -rf audio_cache/
	rm .coverage

docker-build:
	docker build -t balaambot:latest .

HOST_CACHED_DIR=$(PWD)/audio_cache
PERSISTENT_DIR=$(PWD)/persistent

docker-run:
	@mkdir -p $(HOST_CACHED_DIR)
	@mkdir -p $(PERSISTENT_DIR)
	docker run --rm -it \
		--env-file .env \
		-v $(HOST_CACHED_DIR):/app/audio_cache \
		-v $(PERSISTENT_DIR):/app/persistent \
		balaambot:latest

docker-brun: docker-build docker-run

test:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration
