.PHONY: install lint run clean unpack

install:
	poetry install

install-dev:
	poetry install --all-groups

lint:
	ruff check .

build:
	poetry build

run:
	poetry run balaambot

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

docker-run:
	docker run --rm -it balaambot:latest

docker-brun: docker-build docker-run

test:
	poetry run pytest -m "not integration"

test-integration:
	poetry run pytest -m integration
