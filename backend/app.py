from fastapi import FastAPI, HTTPException
from fastapi import Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor
from geopy.distance import geodesic
import geojson
import redis
import psycopg2
import json
import logging
from shapely.geometry import shape

# Set up basic logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")





app = FastAPI()

# Allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis
r = redis.Redis(host='localhost', port=6379, db=0)
r.flushall()
# Postgres
conn = psycopg2.connect(
    database="geodata",
    user="postgres",
    password="qwerty",
    host="localhost",
    port="5432"
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

def fetch_from_db(layer_type: str, name: str, year=2023):
    query = """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection', 
        'features', COALESCE(jsonb_agg(feature), '[]'::jsonb)
    )
    FROM (
        SELECT jsonb_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(geom)::jsonb,
            'properties', to_jsonb(row) - 'geom'
        ) AS feature
        FROM (
            SELECT * FROM demographics
            WHERE layer_type = %s
              AND name ILIKE %s
              AND (year = %s OR year IS NULL)
        ) row
    ) features;
    """
    if layer_type =='city':
        cursor.execute(query, (layer_type, f"%{name}%", None))
    else:
        cursor.execute(query, (layer_type, f"%{name}%", year))
    result = cursor.fetchone()
    return result

@app.get("/geojson/{layer_type}/{name}")
def get_geojson(layer_type: str, name: str):
    key = f"{layer_type.lower()}:{name.lower()}"
    
    cached_data = r.get(key)
    if cached_data:
        print("✅ Serving from cache")
        return JSONResponse(content=json.loads(cached_data))
    else:
        result = fetch_from_db(layer_type, name)
        
        if result:
            r.set(key, json.dumps(result), ex=3600)
            print(f"🔄 Fetched from DB and cached: {result}")  # Log the DB result
            return JSONResponse(content=result)
        else:
            print("❌ No result found in DB")
            raise HTTPException(status_code=404, detail="Not found")




#-----------------------------------------------------------------------------------
                            # Nearby Cities

# Assuming `cursor` is already created and connected

# Function to fetch state boundary
def fetch_state_boundary(state_name):
    query = """
    SELECT ST_AsGeoJSON(geom) AS geom
    FROM demographics
    WHERE (name ILIKE %s OR stusps ILIKE %s)
      AND layer_type = 'state'
    LIMIT 1;
    """
    cursor.execute(query, (state_name, state_name))
    result = cursor.fetchone()
    if result and result.get("geom"):
        return geojson.loads(result["geom"])  # Return as GeoJSON
    return None

# Function to fetch city centroid (point location)
def fetch_city_point(city_name):
    query = """
    SELECT ST_AsGeoJSON(ST_Centroid(geom)) AS centroid
    FROM demographics
    WHERE full_name ILIKE %s
      AND layer_type = 'place'
    LIMIT 1;
    """
    cursor.execute(query, (f"%{city_name}%",))
    result = cursor.fetchone()
    if result and result.get("centroid"):
        return geojson.loads(result["centroid"])  # Return as GeoJSON
    return None

# Function to fetch nearby cities outside a state boundary
def fetch_nearby_cities_outside_state(state_geom_geojson, distance_km=50):
    query = """
    SELECT full_name, ST_Distance(c.geom::geography, s.geom::geography) AS distance_meters
    FROM demographics AS c, (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom) AS s
    WHERE c.layer_type = 'place'
      AND NOT ST_Intersects(c.geom, s.geom)
      AND ST_DWithin(c.geom::geography, s.geom::geography, %s)
    ORDER BY distance_meters
    LIMIT 50;
    """
    cursor.execute(query, (geojson.dumps(state_geom_geojson), distance_km * 1000))
    return cursor.fetchall()

# Function to fetch nearby cities around a given city
def fetch_nearby_cities_around_city(city_point_geojson, distance_km=50):
    try:
        # Debugging: Print the GeoJSON to ensure it's correct
        logger.info(f"GeoJSON received: {city_point_geojson}")
        
        # Execute query
        query = """
        SELECT name, ST_Distance(c.geom::geography, s.centroid::geography) AS distance_meters
        FROM demographics AS c, (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS centroid) AS s
        WHERE c.layer_type = 'city'
          AND ST_DWithin(c.geom::geography, s.centroid::geography, %s)
          AND ST_Distance(c.geom::geography, s.centroid::geography) > 0
        ORDER BY distance_meters
        LIMIT 30;
        """
        
        # Check if GeoJSON is properly formatted
        try:
            geojson_str = geojson.dumps(city_point_geojson)
            logger.info(f"GeoJSON string: {geojson_str}")
        except Exception as e:
            logger.error(f"Error serializing GeoJSON: {e}")
            return []
        
        cursor.execute(query, (geojson_str, distance_km * 1000))
        
        # Fetch results
        results = cursor.fetchall()
        
        # Debugging: Log the results to check
        if not results:
            logger.warning(f"No nearby cities found within {distance_km} km")
        else:
            logger.info(f"Found {len(results)} nearby cities.")
        
        return results

    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return []



@app.get("/geojson/nearby_cities/{layer}/{name}")
def get_nearby_cities(name: str,layer:str):
    try:
        logger.info(f"Fetching nearby cities for: {name}")
        result = None
        key = f"{layer.lower()}:{name.lower()}"
        result=r.get(key)
        if result:
            result = json.loads(result)
            geojson_geometry = result["jsonb_build_object"]["features"][0]["geometry"]
            logger.info(geojson_geometry)
            rr=fetch_nearby_cities_around_city(geojson_geometry);
            print(f"{rr} Nearby Cities")
            unique_names = list(set(row['name'] for row in rr))
            print(unique_names)

            return {"cities": unique_names}
        else:
            logger.debug(f"No cached data found for key: {key}")

        if not result:
            logger.error(f"No cached data found for any key related to {name}")
            raise HTTPException(status_code=404, detail="City not found in cache")

        # Decode cached data from JSON
        logger.info(f"Decoded cached data successfully.")

        # # Look for the specific city in the features
        # center_city = None
        # for feature in result["features"]:
        #     if feature["properties"].get("name", "").lower() == name.lower():
        #         center_city = feature
        #         break

        # if not center_city:
        #     logger.warning(f"City '{name}' not found in cached features.")
        #     return JSONResponse(content={"type": "FeatureCollection", "features": []})

        # # Get center coordinates and validate geometry type
        # center_coords = center_city["geometry"]["coordinates"]
        # if center_city["geometry"]["type"] == "Point":
        #     center_lon, center_lat = center_coords
        # elif center_city["geometry"]["type"] == "MultiPolygon":
        #     first_polygon = center_coords[0][0][0]
        #     center_lon, center_lat = first_polygon
        # else:
        #     logger.error(f"Unsupported geometry type: {center_city['geometry']['type']}")
        #     raise HTTPException(status_code=500, detail="Unsupported geometry type")

        # logger.info(f"Center city '{name}' located at (lat={center_lat}, lon={center_lon})")

        # # Now, use this point to search nearby cities from DB
        # center_point_geojson = {
        #     "type": "Point",
        #     "coordinates": [center_lon, center_lat]
        # }

        # # Fetch nearby cities within 50km radius
        # nearby_cities_records = fetch_nearby_cities_around_city(center_point_geojson, distance_km=50)

        # features = []
        # for record in nearby_cities_records:
        #     features.append({
        #         "type": "Feature",
        #         "geometry": {
        #             "type": "Point",  # Assuming city centroids
        #             "coordinates": [record["longitude"], record["latitude"]]  # Ensure coordinates are included
        #         },
        #         "properties": {
        #             "name": record["full_name"],
        #             "distance_meters": record["distance_meters"]
        #         }
        #     })

        # logger.info(f"Found {len(features)} nearby cities within 50km.")

        # return JSONResponse(content={
        #     "type": "FeatureCollection",
        #     "features": features
        # })

    except Exception as e:
        logger.exception(f"Error fetching nearby cities: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")




def fetch_msa_or_county(latitude, longitude, layer, name):
    if layer == 'city':
        query = """
        SELECT name 
        FROM demographics
        WHERE ST_Contains(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
        AND layer_type = 'county';
        """
        cursor.execute(query, (longitude, latitude))

    elif layer == 'state':
        name = f"%{name}%"  # wildcard match
        query = """
        SELECT name 
        FROM demographics
        WHERE layer_type = 'county'
        AND full_name ILIKE %s;
        """
        cursor.execute(query, (name,))
        
    else:
        raise ValueError("Invalid layer type. Expected 'city' or 'state'.")
    
    return cursor.fetchall()



@app.get("/geojson/msas/{layer_type}/{name}")
def get_msa_or_county(name: str):
    cached_data = None
    for layer_type in ['city', 'county', 'state']:
        key = f"{layer_type.lower()}:{name.lower()}"
        cached_data = r.get(key)
        if cached_data:
            cached_data = json.loads(cached_data)  # Ensure the cached data is deserialized from JSON
            break

    if not cached_data:
        logger.error(f"No cached data found for key: {key}")
        raise HTTPException(status_code=404, detail="City not found in cache")

    geometry = cached_data.get("jsonb_build_object")
    if not geometry:
        logger.error("No geometry found in cached data.")
        raise HTTPException(status_code=500, detail="Invalid cached data structure")

    # Extract MultiPolygon geometry
    multi_polygon = geometry["features"][0]["geometry"]
    print(multi_polygon)
    # Create the Shapely geometry object
    shapely_geometry = shape(multi_polygon)

    # Calculate the centroid of the MultiPolygon
    centroid = shapely_geometry.centroid
    centroid_lon, centroid_lat = centroid.x, centroid.y
    print(f"Centroid Latitude: {centroid_lat}, Centroid Longitude: {centroid_lon}, {layer_type},{name}")
    
    # Fetch MSA or county regions using the calculated centroid coordinates
    regions = fetch_msa_or_county( centroid_lat,centroid_lon,layer_type,name)
    unique_names = list(set(row['name'] for row in regions))
    print(unique_names)

    return {"regions": unique_names}

    #--------------------------------------------------------TRENDS----------------------------------------------
@app.get("/demographics/trend/{layer_type}/{name}")

def get_demographic_trend(layer_type: str, name: str, field: str = Query(...)):
    try:
        # Validate allowed fields to prevent SQL injection
        allowed_fields = ["population", "education_total", "bachelor_degree", "masters_degree", "population_below_poverty_level"]
        print("HELLOOOO")
        if field not in allowed_fields:
            raise HTTPException(status_code=400, detail=f"Invalid field: {field}")

        query = f"""
            SELECT year, {field}
            FROM demographics
            WHERE layer_type = %s
              AND name ILIKE %s
              AND year IS NOT NULL
            ORDER BY year;
        """

        cursor.execute(query, (layer_type, f"%{name}%"))
        trend_data = cursor.fetchall()

        if not trend_data:
            print(f"No demographic trend data found for {name}.")
            raise HTTPException(status_code=404, detail="Trend data not found")

        trend = []
        for row in trend_data:
            trend.append({
                "year": row["year"],
                field: row[field]  # Dynamically add the requested field
            })

        return {"trend": trend}

    except Exception as e:
        print(f"Error fetching demographic trend: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")









