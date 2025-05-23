.PHONY: install lint run clean unpack

install:
	poetry install

lint:
	ruff check .

run:
	poetry run python src/main.py

unpack:
	unzip sounds.zip

clean:
	@echo "Cleaning up..."
	# Remove Python bytecode and __pycache__ directories
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	# Remove Ruff cache
	rm -rf .ruff_cache
	# Remove build artifacts
	rm -rf build/ dist/ *.egg-info
