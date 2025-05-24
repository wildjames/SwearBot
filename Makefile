.PHONY: install lint run clean unpack

install:
	poetry install

lint:
	ruff check .

run:
	poetry run python src/main.py

unpack:
	unzip -u sounds.zip

clean:
	@echo "Cleaning up..."
	# Remove Python bytecode and __pycache__ directories
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	# Remove Ruff cache
	rm -rf .ruff_cache
	# Remove build artifacts
	rm -rf build/ dist/ *.egg-info

docker-build:
	docker build -t swearbot:latest .

docker-run:
	docker run --rm -it swearbot:latest

docker-brun: docker-build docker-run
