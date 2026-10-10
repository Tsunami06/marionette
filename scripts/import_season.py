"""Normalize a reviewed season-reference download; never enable live execution."""
import argparse
import hashlib
import json
from pathlib import Path


def normalize(raw, digest, fetched_at):
    if raw.get("season_id") != "s18" or raw.get("game_version") != "18.18.3":
        raise ValueError("This importer only accepts the reviewed s18 / 18.18.3 archive")
    traits = {str(row["id"]): row for row in raw["traits"]}
    champions = []
    for row in raw["champions"]:
        trait_ids = [str(value) for value in row["trait_ids"]]
        champions.append({
            "id": str(row["id"]), "name": row["name"], "cost": row["cost"],
            "trait_ids": trait_ids,
            "traits": [traits[value]["name"] for value in trait_ids],
            "variant": next((traits[value]["name"] for value in trait_ids
                             if value != "469"), None) if row["name"] == "拉克丝" else None,
            "skill": {key: row.get("skill", {}).get(key) for key in ("name", "description")},
        })
    charms = []
    for mechanic in raw.get("mechanics", []):
        if mechanic.get("kind") != "charm":
            continue
        for row in mechanic["entries"]:
            data = row["data"]
            charms.append({
                "id": str(row["id"]), "name": row["name"], "cost": data.get("cost"),
                "description": row.get("description"), "category": data.get("category"),
                "upgrade": data.get("upgrade"), "prismatic": data.get("prismatic"),
                "reference_rounds": data.get("rounds", []),
                "reference_requires": data.get("requires", []),
                "provenance": row.get("extensions", {}).get("provenance"),
            })
    return {
        "schema_version": 1,
        "metadata": {
            "season_id": raw["season_id"], "season": raw["display_name"],
            "patch": "18.3", "source_version": raw["game_version"],
            "fetched_at": fetched_at, "source_sha256": digest,
            "source_url": "https://jcc.np5.top/tools/seasons/s18",
            "source_data_url": "https://jcc.np5.top/season-assets/6435bcc2816e4a7f952fcb8b095abef2/data/index.json?v=s18__18_18_3",
            "official_patch_url": "https://www.taptap.cn/moment/853961338387434337",
            "official_intro_repost_url": "https://www.taptap.cn/moment/838820403475382937",
            "verification": "reference_only", "device_verified": False,
            "notes": [
                "Normalized factual reference from a community dataset; not an official API.",
                "Source version 18.18.3 is an archive label, not the official patch name.",
                "Skill text and numerical effects are unverified reference, not an action policy.",
                "Charm rounds/requirements may be inherited from older patches; retain field provenance.",
                "169 base charm entries do not constitute an exhaustive verified list.",
                "Equipment data is not supplied by this dataset.",
            ],
        },
        "champions": champions,
        "traits": [{key: row.get(key) for key in ("id", "name", "category", "description", "breakpoints")}
                   for row in raw["traits"]],
        "augments": [{key: row.get(key) for key in ("id", "name", "description", "tier", "appearance_stages", "extensions")}
                     for row in raw.get("augments", [])],
        "charms": charms,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fetched-at", required=True)
    args = parser.parse_args()
    payload = args.input.read_bytes()
    result = normalize(json.loads(payload), hashlib.sha256(payload).hexdigest(), args.fetched_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
