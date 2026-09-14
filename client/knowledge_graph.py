"""Lightweight entity and relationship extraction for Knowledge Graph memory."""
import re
from typing import Dict, List, Tuple


def extract_entities_and_relations(text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Extracts semantic entities and directional relations from unstructured text.
    Zero external dependencies, fast, deterministic.
    """
    if not text or not isinstance(text, str):
        return [], []

    # 1. Explicit wikilinks: [[Entity Name]]
    explicit = re.findall(r'\[\[(.*?)\]\]', text)
    # 2. Backticked technical identifiers: `Qdrant`, `fleet_memory`
    backticked = re.findall(r'`([A-Za-z0-9_\-\.]{2,35})`', text)
    # 3. Capitalized named entities
    proper_nouns = re.findall(r'\b[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)*\b', text)

    stop_words = {
        "The", "This", "When", "Then", "With", "From", "Here", "There", "What", "That",
        "True", "False", "None", "Warning", "Error", "Note", "Check", "Run", "User", "System",
        "Please", "Also", "Just", "Have", "Been", "Will", "Would", "Could", "Should"
    }

    raw_entities = [e.strip() for e in explicit if e.strip()] + \
                   [b.strip() for b in backticked if b.strip() and b not in stop_words] + \
                   [p.strip() for p in proper_nouns if p.strip() and p not in stop_words and len(p.strip()) > 2]

    # Deduplicate while preserving order
    entities = list(dict.fromkeys(raw_entities))[:15]

    # Extract relational triples between identified entities
    relations: List[Dict[str, str]] = []
    verbs = ["runs on", "connects to", "uses", "integrates with", "stores in", "communicates with", "authorizes", "depends on", "belongs to"]
    verb_regex = r'\b(' + '|'.join(verbs) + r')\b'

    for i, ent1 in enumerate(entities):
        for ent2 in entities[i+1:]:
            pattern = rf'\b{re.escape(ent1)}\b.*?{verb_regex}.*?\b{re.escape(ent2)}\b'
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                relations.append({
                    "source": ent1,
                    "relation": m.group(1).lower().replace(" ", "_"),
                    "target": ent2
                })

    return entities, relations[:15]
