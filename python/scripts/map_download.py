import overpy
import geojson
import xml.etree.ElementTree as ET

def filter_city_with_overpass(city: str):
    match city:
        case "Porto":
            osm_id = 3459013
        case "Sydney":
            osm_id = 5750005
        case _:
            raise ValueError(f"City {city} not supported.")
    
    id = 3600000000 + osm_id

    api = overpy.Overpass()

    query = f"""
    [timeout:900];
    area({id});
    (
    way(area)
    ['name']
    ['highway'];
    );
    (._;>;);
    out;
    """

    result = api.query(query)

    features = []

    # Process nodes
    for node in result.nodes:
        point = geojson.Point((float(node.lon), float(node.lat)))
        features.append(geojson.Feature(id=node.id, geometry=point, properties=node.tags))

    # Process ways
    for way in result.ways:
        # Create a LineString from the way's nodes
        coordinates = [(float(node.lon), float(node.lat)) for node in way.nodes]
        line = geojson.LineString(coordinates)
        features.append(geojson.Feature(id=way.id, geometry=line, properties=way.tags))

    # Create a GeoJSON FeatureCollection
    feature_collection = geojson.FeatureCollection(features)

    # Save to a GeoJSON file
    with open(f"{city}.geojson", "w") as f:
        geojson.dump(feature_collection, f)

if __name__ == "__main__":
    # filter_city_with_overpass("Porto")
    filter_city_with_overpass("Sydney")

