import logging
import pathlib

import pydantic

import balaambot.config

logger = logging.getLogger(__name__)

SAVE_FILE = pathlib.Path(balaambot.config.PERSISTENT_DATA_DIR) / "cats.json"

# TODOs:
# Key cats by discord server
# fuzzy search for cat names (try pkg: the fuzz)
# move message strings to separate file (cat_commands_strings.py?)


class Cat(pydantic.BaseModel):
    """Data representing a cat."""

    name: str


class CatData(pydantic.BaseModel):
    """Data class holding cats indexed by server and cat name."""

    cats: dict[str, Cat]


class CatHandler:
    """Main class for handling cat interactions."""

    def __init__(self) -> None:
        """Initialize the CatHandler."""
        self.db = self._load_cat_db()

    def get_num_cats(self) -> int:
        """How many cats there are.

        Returns:
            int: Number of cats

        """
        return len(self.db.cats)

    def get_cat(self, cat_name: str) -> str | None:
        """Check if cat exists and return their name if they do.

        Args:
            cat_name (str): Cat name to check

        Returns:
            str: The cat's official name
            None: Cat doesn't exist

        """
        cat_id = self._get_cat_id(cat_name)
        if cat_id in self.db.cats:
            return self.db.cats[cat_id].name
        return None

    def get_cat_names(self) -> str:
        """Get a formatted list of cat names."""
        return "\n".join(f"- {cat.name}" for cat in self.db.cats.values())

    def add_cat(self, cat_name: str) -> None:
        """Creates a new cat.

        Args:
            cat_name (str): The name of the cat to create

        """
        cat_id = self._get_cat_id(cat_name)
        # Make a new cat and save it
        self.db.cats[cat_id] = Cat(name=cat_name)
        self._save_cat_db(self.db)

    def _get_cat_id(self, cat_name: str) -> str:
        return cat_name.strip().lower()

    def _load_cat_db(self) -> CatData:
        """Load cats from the save file."""
        if not SAVE_FILE.exists():
            logger.info("No save file found at %s", SAVE_FILE)
            return CatData(cats={})

        with SAVE_FILE.open("r") as f:
            try:
                json_data = f.read()
                db = CatData.model_validate_json(json_data)
            except pydantic.ValidationError:
                logger.exception(
                    "Failed to decode CatData from: %s\nCreating new one.", SAVE_FILE
                )
                return CatData(cats={})
            logger.info("Loaded %d cat(s) from %s", len(db.cats), SAVE_FILE)
            return db

    def _save_cat_db(self, db: CatData) -> None:
        """Save cats to the save file."""
        if not SAVE_FILE.exists():
            logger.info("No save file found, creating a new one.")
            SAVE_FILE.touch()
        # Save as JSON
        with SAVE_FILE.open("w") as f:
            f.write(db.model_dump_json(indent=4))
        logger.info("Saved %d cat(s) to %s", len(db.cats), SAVE_FILE)
