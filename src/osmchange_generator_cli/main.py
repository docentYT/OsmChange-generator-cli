import typer
from rich import print
import os
import json
from osm_easy_api.data_classes import OsmChange, Node, Way, Action, Tags

app = typer.Typer()

def load_features_from_file(file_name: str, tag: str, log: bool) -> dict[str, str]:
    features = {}
    with open(file_name, "r", encoding="utf8") as file:
            data = json.loads(file.read())
            for feature in data["features"]:
                if feature["properties"].get(tag):
                    features[feature["properties"][tag]] = feature
                else:
                    if log: print(f"[bold yellow]Warning:[/bold yellow] Missing [bold]{tag}[/bold] in {file_name} for feature:", feature)
    return features

Pairs = dict[str, dict[str, dict[str, str] | dict[str, str]]]
def find_pairs(input_features, osm_features) -> Pairs:
    pairs = {}
    for k, v in input_features.items():
        pairs.update({
            k: {
                "first": v,
                "second": osm_features.pop(k) if osm_features.get(k) else None
                }
        })

    for k, v in osm_features.items():
        pairs.update({
            k: {
                "first": None,
                "second": v
                }
        })
    
    return pairs

def parse_geojson_feature(feature: dict) -> Node | Way:
    type = feature["geometry"]["type"]
    p = feature["properties"]
    id = None
    if p.get("@id"):
        id = p["@id"].split('/')[1]
        p.pop("@id")
    version = 1 if id else None
    match type:
        case "Point":
            return Node(id=id, version=version, tags=Tags(p), latitude=feature["geometry"]["coordinates"][1], longitude=feature["geometry"]["coordinates"][0])
        case "LineString" | "Polygon":
            nodes = []
            for node in feature["geometry"]["coordinates"]:
                nodes.append(Node(version=1, latitude=node[1], longitude=node[0]))
            return Way(id=id, version=version, tags=Tags(p), nodes=nodes)
        case _:
            raise ValueError(f"Unsupported type: {type}")


@app.command()
def main(input_data_file_names: list[str], osm_data_file_name: str, output_file_name: str, tag: str, log: bool = True, create: bool = False, delete: bool = False, changeset_id: int = 1):
    """
    --input_data_file_names and --osm_data_file_name should be in geojson format.
    """
    input_features = {}
    for file_name in input_data_file_names:
        input_features.update(load_features_from_file(file_name, tag, log))
    
    osm_features = {}
    osm_features.update(load_features_from_file(osm_data_file_name, tag, log))

    pairs = find_pairs(input_features, osm_features)

    osmChange = OsmChange("0.6", "OsmChange-generator-cli", "0")

    for k, v in pairs.items():
        first = parse_geojson_feature(v["first"]) if v.get("first") else None
        second = parse_geojson_feature(v["second"]) if v.get("second") else None

        if not second and create:
            assert(first)
            osmChange.add(first, Action.CREATE)
            continue

        if not first and delete:
            assert(second)
            osmChange.add(second, Action.DELETE)
            continue
        

    with open(os.path.join(output_file_name), "w", encoding="utf8") as file:
        file.write(osmChange.to_xml(changeset_id))
    if log: print(f"[bold blue]INFO:[/bold blue] [bold]OsmChange[/bold] saved to [bold]{output_file_name}[/bold]")

if __name__ == "__main__":
    typer.run(main)