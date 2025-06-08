import json
import logging
import pathlib

import pydantic

import balaambot.config

logger = logging.getLogger(__name__)

SAVE_FILE = pathlib.Path(balaambot.config.PERSISTENT_DATA_DIR) / "cats.json"

# TODOs:
# Use one model for everything to save together
# Key cats by discord server
# fuzzy search for cat names (try pkg: the fuzz)
# move message strings to separate file (cat_commands_strings.py?)


class Cat(pydantic.BaseModel):
    """Data representing a cat."""

    name: str


# class CatData(pydantic.BaseModel):
#     """Data class holding cats indexed by server and cat name."""

#     cats: dict[str, dict[str, Cat]]


class CatHandler:
    """Main class for handling cat interactions."""

    def __init__(self) -> None:
        """Initialize the CatHandler."""
        self.cats = self._load_cats()

    def get_num_cats(self) -> int:
        """How many cats there are.

        Returns:
            int: Number of cats

        """
        return len(self.cats)

    def get_cat(self, cat_name: str) -> str | None:
        """Check if cat exists and return their name if they do.

        Args:
            cat_name (str): Cat name to check

        Returns:
            str: The cat's official name
            None: Cat doesn't exist

        """
        cat_id = self._get_cat_id(cat_name)
        if cat_id in self.cats:
            return self.cats[cat_id].name
        return None

    def get_cat_names(self) -> str:
        """Get a formatted list of cat names."""
        return "\n".join(f"- {cat.name}" for cat in self.cats.values())

    def add_cat(self, cat_name: str) -> None:
        """Creates a new cat.

        Args:
            cat_name (str): The name of the cat to create

        """
        cat_id = self._get_cat_id(cat_name)
        # Make a new cat and save it
        self.cats[cat_id] = Cat(name=cat_name)
        self._save_cats(self.cats)

    def _get_cat_id(self, cat_name: str) -> str:
        return cat_name.strip().lower()

    def _load_cats(self) -> dict[str, Cat]:
        """Load cats from the save file."""
        cats = {}
        if SAVE_FILE.exists():
            with SAVE_FILE.open("r") as f:
                try:
                    cat_data = json.load(f)
                    cats = {k: Cat(**v) for k, v in cat_data.items()}
                    logger.info("Loaded %d cat(s) from %s", len(cats), SAVE_FILE)
                except json.JSONDecodeError:
                    logger.exception("Failed to decode JSON from %s", SAVE_FILE)
        else:
            logger.info("No save file found at %s", SAVE_FILE)
        return cats

    def _save_cats(self, cats: dict[str, Cat]) -> None:
        """Save cats to the save file."""
        if not SAVE_FILE.exists():
            logger.info("No save file found, creating a new one.")
            SAVE_FILE.touch()
        # Convert each Cat model to a dict
        cats_dict = {k: v.model_dump() for k, v in cats.items()}
        with SAVE_FILE.open("w") as f:
            json.dump(cats_dict, f, indent=4)
        logger.info("Saved %d cat(s) to %s", len(cats_dict), SAVE_FILE)
