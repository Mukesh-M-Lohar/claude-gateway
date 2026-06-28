.PHONY: help install setup-docker docs-serve

# Default target displays help
help:
	@echo "Claude Gateway Development Automations"
	@echo "--------------------------------------"
	@echo "Available commands:"
	@echo "  make install       - Set up development environment (uv, Python, venv, deps, .env)"
	@echo "  make setup-docker  - Build and run the gateway services inside Docker"
	@echo "  make docs-serve    - Serve the documentation locally via MkDocs"

install:
	@echo "==> Checking for 'uv' installation..."
	@if ! which uv > /dev/null 2>&1; then \
		echo "==> 'uv' not found. Installing 'uv' via official installer..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		export PATH="$$HOME/.local/bin:$$PATH"; \
	else \
		echo "==> 'uv' is already installed."; \
	fi
	@echo "==> Creating virtual environment (.venv) and installing Python 3.12..."
	@uv venv --python 3.12 --allow-existing
	@echo "==> Installing workspace dependencies..."
	@uv pip install -r requirements.txt
	@echo "==> Installing development packages..."
	@uv pip install -e ".[dev,docs]"
	@echo "==> Configuring environment variables..."
	@if [ ! -f .env ]; then \
		echo "==> Copying .env.example to .env..."; \
		cp .env.example .env; \
	else \
		echo "==> .env file already exists. Skipping copy."; \
	fi
	@echo ""
	@echo "==> Setup complete! To activate the environment, run:"
	@echo "    source .venv/bin/activate"

setup-docker:
	@echo "==> Starting Claude Gateway services in Docker..."
	docker compose up -d --build

docs-serve:
	@echo "==> Starting MkDocs server..."
	@.venv/bin/mkdocs serve
