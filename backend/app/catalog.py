"""PartsRepository: the single data-access layer for the agent's tools.

Everything the tools need (lookup, search, compatibility, repair help)
goes through this class. It reads cached JSON that grows over time as
parts/models are fetched live from PartSelect.

It also produces the structured "cards" the frontend renders. The agent's tools
return a short text summary for the model PLUS these cards for the UI, so the
model narrates while the UI renders rich, grounded components.
"""
import json
import os
from typing import List, Optional

from .config import DATA_DIR, settings
from .live import PartSelectClient
from .search import SearchIndex


def _load(name: str):
    with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(name: str, data) -> None:
    """Atomic-ish write of a data file (write temp, then replace)."""
    path = DATA_DIR / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


class PartsRepository:
    def __init__(self, persist: bool = True):
        self.persist = persist
        self.parts: List[dict] = _load("parts.json")
        self.models = {m["model_number"].upper(): m for m in _load("models.json")}

        self._by_ps = {p["ps_number"].upper(): p for p in self.parts}
        self._by_mfr = {p["mfr_number"].upper(): p for p in self.parts}
        self.index = SearchIndex(self.parts)

        self.live = PartSelectClient(
            enabled=settings.live_fetch,
            delay=settings.live_delay,
            cache_dir=settings.live_cache_dir,
            resolve_via_sitemap=settings.live_resolve_via_sitemap,
        )
        self._live_models: dict = {}

    def _remember_part(self, part: dict) -> dict:
        """Index a live-fetched part so subsequent lookups/search hit the cache,
        and persist it to parts.json so the data folder grows over time."""
        key = part["ps_number"].upper()
        if key not in self._by_ps:
            self._by_ps[key] = part
            if part.get("mfr_number"):
                self._by_mfr[part["mfr_number"].upper()] = part
            self.parts.append(part)
            self.index = SearchIndex(self.parts)
            if self.persist:
                try:
                    _save("parts.json", self.parts)
                except Exception:
                    pass
        return self._by_ps[key]

    def _enrich_part(self, part: dict) -> dict:
        """If a cached part is sparse (from a model-page listing), fetch the
        full part page to fill in price, description, install, etc."""
        if not self.live.enabled:
            return part
        if part.get("price") and part.get("description") and part.get("install"):
            return part
        ps = part["ps_number"]
        url = part.get("url")
        fetched = self.live.fetch_part(ps, url=url)
        if not fetched:
            return part
        for k, v in fetched.items():
            if v and (not part.get(k) or (k == "price" and not part[k])):
                part[k] = v
        if self.persist:
            try:
                _save("parts.json", self.parts)
            except Exception:
                pass
        return part

    def _remember_model(self, model: dict) -> None:
        """Persist a live-fetched model to models.json (cache grows over time)."""
        key = model["model_number"].upper()
        if key not in self.models:
            self.models[key] = model
            if self.persist:
                try:
                    _save("models.json", list(self.models.values()))
                except Exception:
                    pass

    # ---- lookups -------------------------------------------------------
    def get_part(self, part_number: str, enrich: bool = False) -> Optional[dict]:
        if not part_number:
            return None
        key = part_number.strip().upper().replace(" ", "")
        local = self._by_ps.get(key) or self._by_mfr.get(key)
        if local:
            if enrich:
                return self._enrich_part(local)
            return local
        if self.live.enabled and key.startswith("PS"):
            fetched = self.live.fetch_part(key)
            if fetched:
                return self._remember_part(fetched)
        return None

    def get_model(self, model_number: str) -> Optional[dict]:
        if not model_number:
            return None
        key = model_number.strip().upper().replace(" ", "")
        local = self.models.get(key)
        if local:
            return local
        live = self._get_live_model(key)
        return live["model"] if live else None

    def _get_live_model(self, model_key: str) -> Optional[dict]:
        """Fetch (and cache) a model + its parts from the live site."""
        if not self.live.enabled:
            return None
        if model_key in self._live_models:
            return self._live_models[model_key]
        result = self.live.fetch_model(model_key)
        if result:
            for p in result["parts"]:
                self._remember_part(p)
            self._remember_model(result["model"])
            self._live_models[model_key] = result
        return result

    def search_parts(self, query, appliance_type=None, brand=None, limit=5) -> List[dict]:
        return self.index.search(query, appliance_type=appliance_type, brand=brand, limit=limit)

    # ---- compatibility -------------------------------------------------
    def check_compatibility(self, part_number: str, model_number: str) -> dict:
        model_key = (model_number or "").strip().upper().replace(" ", "")
        model = self.models.get(model_key)

        live_model = None
        if model is None and self.live.enabled:
            live = self._get_live_model(model_key)
            if live:
                live_model = live["model"]

        part = self.get_part(part_number)
        if not part:
            return {"status": "part_not_found", "part_number": part_number}

        direct = model_key in [m.upper() for m in part.get("compatible_models", [])]
        via_model = bool(model and part["ps_number"] in model.get("compatible_parts", []))
        compatible = direct or via_model

        if not compatible and live_model is not None:
            if part["ps_number"].upper() in [p.upper() for p in live_model["compatible_parts"]]:
                return {
                    "status": "ok", "compatible": True, "part": part,
                    "model_number": model_number, "model_known": True,
                    "reason": (
                        f"{part['name']} (PartSelect #{part['ps_number']}) is listed "
                        f"among the parts for model {model_number} on PartSelect."
                    ),
                }

        result = {
            "status": "ok",
            "compatible": compatible,
            "part": part,
            "model_number": model_number,
            "model_known": model is not None or live_model is not None,
        }
        if compatible:
            result["reason"] = (
                f"{part['name']} (PartSelect #{part['ps_number']}) is confirmed "
                f"compatible with model {model_number}."
            )
        elif live_model is not None:
            result["compatible"] = None
            result["reason"] = (
                f"{part['name']} doesn't appear in the parts listed for "
                f"{model_number} ({live_model['brand']} {live_model['appliance_type']}), "
                f"so I can't confirm it fits. Double-check the model's full parts list."
            )
        elif model is None:
            result["reason"] = (
                f"Model {model_number} isn't in our records, so compatibility can't "
                f"be confirmed automatically. {part['name']} works with: "
                f"{', '.join(part.get('compatible_products', []))}."
            )
        else:
            result["reason"] = (
                f"{part['name']} is not listed as compatible with {model_number} "
                f"({model['brand']} {model['appliance_type']})."
            )
            alt = self._alternative_for_model(model, part.get("category"))
            if alt:
                result["alternative"] = alt
        return result

    def _alternative_for_model(self, model: dict, category: Optional[str]) -> Optional[dict]:
        for ps in model.get("compatible_parts", []):
            cand = self._by_ps.get(ps.upper())
            if cand and (category is None or cand.get("category") == category):
                return cand
        for ps in model.get("compatible_parts", []):
            cand = self._by_ps.get(ps.upper())
            if cand:
                return cand
        return None

    def parts_for_model(self, model_number: str, category: str = None) -> dict:
        model = self.get_model(model_number)
        if not model:
            return {"status": "model_not_found", "model_number": model_number}
        parts = []
        for ps in model.get("compatible_parts", []):
            p = self._by_ps.get(ps.upper())
            if p:
                parts.append(p)
        if category:
            parts = [p for p in parts if category.lower() in p.get("category", "").lower()]
        return {"status": "ok", "model": model, "parts": parts}

    # ---- repair help ---------------------------------------------------
    def find_repair_help(self, appliance_type: str, symptom: str, brand: str = None) -> dict:
        """Search for parts that fix a symptom via live PartSelect /Repair/ pages."""
        if self.live.enabled and appliance_type:
            symptoms_list = self.live.fetch_repair_symptoms(appliance_type)
            if symptoms_list:
                return {"source": "symptom_list", "parts": [], "guide": None,
                        "symptoms": symptoms_list, "appliance_type": appliance_type}
        return {"source": "none", "parts": [], "guide": None}

    def fetch_symptom_repair_guide(self, symptom_url: str) -> Optional[dict]:
        """Fetch a specific symptom detail page from PartSelect."""
        return self.live.fetch_symptom_detail(symptom_url)

    def fetch_model_symptoms(self, model_number: str) -> list[dict]:
        """Return the symptom list for a specific model. Uses cached data
        from models.json if available, otherwise fetches live."""
        key = (model_number or "").strip().upper().replace(" ", "")
        model = self.models.get(key)
        if model and model.get("symptoms"):
            return model["symptoms"]
        symptoms = self.live.fetch_model_symptoms(model_number)
        if symptoms:
            if not model:
                model = self.get_model(model_number)
            if not model:
                model = {"model_number": key, "brand": "", "appliance_type": "",
                         "compatible_parts": [], "verified": True, "source": "live"}
                self._remember_model(model)
            model["symptoms"] = symptoms
            self._persist_models()
        return symptoms

    def fetch_model_symptom_parts(self, model_number: str, symptom_url: str) -> Optional[list]:
        """Fetch parts that fix a specific symptom on a specific model."""
        key = (model_number or "").strip().upper().replace(" ", "")
        model = self.models.get(key)

        result = self.live.fetch_model_symptom_parts(symptom_url)
        if not result or not result.get("parts"):
            return None

        if not model:
            model = {"model_number": key, "brand": "", "appliance_type": "",
                     "compatible_parts": [], "verified": True, "source": "live"}
            self._remember_model(model)
        if "symptoms_data" not in model:
            model["symptoms_data"] = {}
        model["symptoms_data"][result["symptom"]] = result["parts"]
        self._persist_models()

        return result["parts"]

    def get_cached_symptom_parts(self, model_number: str, symptom: str) -> Optional[list]:
        """Return cached symptom parts from models.json if available."""
        key = (model_number or "").strip().upper().replace(" ", "")
        model = self.models.get(key)
        if not model or not model.get("symptoms_data"):
            return None
        return model["symptoms_data"].get(symptom)

    def _persist_models(self):
        if self.persist:
            try:
                _save("models.json", list(self.models.values()))
            except Exception:
                pass

    # ---- card builders (UI payloads) -----------------------------------
    @staticmethod
    def to_product_card(part: dict) -> dict:
        return {
            "type": "product",
            "ps_number": part["ps_number"],
            "mfr_number": part["mfr_number"],
            "name": part["name"],
            "brand": part["brand"],
            "appliance_type": part["appliance_type"],
            "category": part.get("category"),
            "price": part.get("price"),
            "in_stock": part.get("in_stock", True),
            "rating": part.get("rating"),
            "review_count": part.get("review_count"),
            "image_url": part.get("image_url"),
            "url": part.get("url"),
            "description": part.get("description", ""),
            "symptoms_fixed": part.get("symptoms_fixed", []),
            "install_difficulty": part.get("install", {}).get("difficulty"),
        }
