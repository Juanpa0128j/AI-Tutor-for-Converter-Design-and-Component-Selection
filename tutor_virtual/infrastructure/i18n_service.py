import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class I18nService:
    """Service to handle internationalization by loading JSON locale files."""
    
    def __init__(self, locale_dir: str = None):
        if locale_dir is None:
            # Default to 'locales' directory relative to this file's parent (infrastructure) -> tutor_virtual -> locales
            # Actually, structure is tutor_virtual/infrastructure/i18n_service.py
            # We want tutor_virtual/locales
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            locale_dir = os.path.join(base_dir, "locales")
            
        self.locale_dir = locale_dir
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.supported_languages = ["en", "es"]
        self._load_locales()
        
    def _load_locales(self):
        """Loads all supported locale files."""
        for lang in self.supported_languages:
            file_path = os.path.join(self.locale_dir, f"{lang}.json")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.translations[lang] = json.load(f)
            except FileNotFoundError:
                logger.warning(f"Locale file not found: {file_path}")
                self.translations[lang] = {}
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for {lang}: {e}")
                self.translations[lang] = {}

    def get_text(self, lang: str, key: str) -> Any:
        """Retrieves text for a given language and key."""
        if lang not in self.translations:
            lang = "en" # Fallback
        
        return self.translations.get(lang, {}).get(key, f"[{key}]")

    def get_all(self, lang: str) -> Dict[str, Any]:
        """Returns the entire dictionary for a language."""
        if lang not in self.translations:
            return self.translations.get("en", {})
        return self.translations[lang]
