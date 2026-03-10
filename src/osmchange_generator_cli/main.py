import typer
from rich import print
import os
import json
from osm_easy_api.data_classes import OsmChange, Node, Way, Action, Tags
from osm_easy_api.api import Api

app = typer.Typer()

def load_features_from_file(file_name: str, tag: str, log: bool) -> dict[str, str]:
    features = {}
    with open(file_name, "r", encoding="utf8") as file:
            df = json.loads(file.read())["features"]
            features = {f[tag]: f for f in df if f.get(tag)} \
                    | {f["properties"][tag]: f for f in df if f["properties"].get(tag)}
            features_missing_tag = [f for f in df if not (f.get(tag) or f["properties"].get(tag))]
            if log and len(features_missing_tag):
                print(f"[bold yellow]Warning:[/bold yellow] Missing [bold]{tag}[/bold] in {file_name} for {len(features_missing_tag)} features:", features_missing_tag)
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
    p = {k: feature["properties"][k] for k in feature["properties"].keys() if k[0] != '@'}
    id = int(feature["id"]) if feature.get("id") and '/' not in feature["id"] else int(feature["id"].split('/')[1]) if feature.get("id") else None
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

def nodes_are_identical(source: Node, ref: Node) -> bool:
    return source.tags == ref.tags \
            and source.latitude == ref.latitude \
            and source.longitude == ref.longitude

def merge_nodes(source: Node, ref: Node, \
        my_uid, _str_tags_to_override, update_from_api, \
        osmApi) -> tuple[Node|None, dict]:

    stats = {"ignored_updates": [], "modifications": 0}

    if update_from_api:
        ref = osmApi.elements.get(Node, ref.id)

    conflicts = ref.user_id != my_uid
    tags_to_override = _str_tags_to_override.split(',')

    if source.latitude != ref.latitude or source.longitude != ref.longitude:
        if conflicts and 'position' not in tags_to_override:
            stats["ignored_updates"].append((ref.id, 'position', ref.user_id))
        else:
            ref.latitude = source.latitude
            ref.longitude = source.longitude
            stats["modifications"] += 1

    for tag in source.tags.keys():
        if not ref.tags.get(tag) or ref.tags[tag] != source.tags[tag]:
            if conflicts and tag not in tags_to_override:
                stats["ignored_updates"].append((ref.id, tag, ref.user_id))
                continue
            ref.tags[tag] = source.tags[tag]
            stats["modifications"] += 1

    return (ref if stats["modifications"] else None, stats)


@app.command()
def main(input_data_file_names: list[str], \
        osm_data_file_name: str, \
        output_file_name: str, \
        tag: str, \
        log: bool = True, \
        create: bool = False, \
        delete: bool = False, \
        modify: bool = False, \
        modify_opts: tuple[int, str, bool] = (-1, "", False), \
        changeset_id: int = 1):
    """
    --input_data_file_names and --osm_data_file_name should be in geojson format.
    --modify-opts is required if --modify is enabled.
    """
    input_features = {}
    for file_name in input_data_file_names:
        input_features.update(load_features_from_file(file_name, tag, log))
    
    osm_features = {}
    osm_features.update(load_features_from_file(osm_data_file_name, tag, log))

    pairs = find_pairs(input_features, osm_features)

    osmChange = OsmChange("0.6", "OsmChange-generator-cli", "0")
    osmApi = Api("https://openstreetmap.org", '') if modify and modify_opts[2] == True else None

    additions = deletions = modifications = modified_objects = 0
    ignored_updates = []
    for k, v in pairs.items():
        first = parse_geojson_feature(v["first"]) if v.get("first") else None
        second = parse_geojson_feature(v["second"]) if v.get("second") else None

        if not second and create:
            assert(first)
            osmChange.add(first, Action.CREATE)
            additions += 1
            continue

        if not first and delete:
            assert(second)
            osmChange.add(second, Action.DELETE)
            deletions += 1
            continue

        if first and second and modify \
                and type(first) is Node and type(second) is Node \
                and not nodes_are_identical(first, second):
            (changed_node, stats) = merge_nodes(first, second, *modify_opts, osmApi)
            ignored_updates += stats["ignored_updates"]
            if changed_node:
                osmChange.add(changed_node, Action.MODIFY)
                modified_objects += 1
                modifications += stats["modifications"]

        
    if log: print(f"[bold blue]INFO:[/bold blue] found {len(pairs)} pairs. {additions} creation, {deletions} deletion, {modifications} modifications on {modified_objects} objects, {len(ignored_updates)} ignored updates ({ignored_updates})")

    with open(os.path.join(output_file_name), "w", encoding="utf8") as file:
        file.write(osmChange.to_xml(changeset_id))
    if log: print(f"[bold blue]INFO:[/bold blue] [bold]OsmChange[/bold] saved to [bold]{output_file_name}[/bold]")

if __name__ == "__main__":
    typer.run(main)
