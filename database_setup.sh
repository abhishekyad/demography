#!/bin/bash
set -e

# Database details
DBNAME="geodata"
USERNAME="postgres"
GEOJSON_FILE1="./counties_with_all_years_demographics.geojson" 
GEOJSON_FILE2="./cities_with_demographics.geojson" 
GEOJSON_FILE3="./states_with_all_years_demographics.geojson"

# 1. Enable PostGIS extension if not already enabled
psql -U "$USERNAME" -d "$DBNAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. Drop and recreate the demographics table
psql -U "$USERNAME" -d "$DBNAME" -c "DROP TABLE IF EXISTS demographics;"

psql -U "$USERNAME" -d "$DBNAME" -c "
CREATE TABLE demographics (
    state VARCHAR PRIMARY KEY,
    county JSONB DEFAULT '[]'::JSONB,
    city JSONB DEFAULT '[]'::JSONB
);
"

# 3. Load states into the demographics table
# Insert each state with empty county and city arrays
psql -U "$USERNAME" -d "$DBNAME" -c "
WITH states_data AS (
    SELECT DISTINCT properties->>'STATEFP' AS statefp
    FROM (
        SELECT jsonb_array_elements((ST_AsGeoJSON(geom)::jsonb)->'features') AS feature
        FROM ogr_fdw_layer
        WHERE filename = '$GEOJSON_FILE3'
    ) AS features
    CROSS JOIN LATERAL (SELECT feature->'properties' AS properties) AS props
)
INSERT INTO demographics (state)
SELECT statefp
FROM states_data;
"

# 4. Insert counties under each state
psql -U "$USERNAME" -d "$DBNAME" -c "
WITH counties_data AS (
    SELECT 
        properties->>'STATEFP' AS statefp,
        jsonb_build_object(
            'PLACEFP', properties->>'PLACEFP',
            'STATEFP', properties->>'STATEFP'
        ) AS county_info
    FROM (
        SELECT jsonb_array_elements((ST_AsGeoJSON(geom)::jsonb)->'features') AS feature
        FROM ogr_fdw_layer
        WHERE filename = '$GEOJSON_FILE1'
    ) AS features
    CROSS JOIN LATERAL (SELECT feature->'properties' AS properties) AS props
)
UPDATE demographics d
SET county = county || county_info
FROM counties_data c
WHERE d.state = c.statefp;
"

# 5. Insert cities under each state
psql -U "$USERNAME" -d "$DBNAME" -c "
WITH cities_data AS (
    SELECT 
        properties->>'STATEFP' AS statefp,
        jsonb_build_object(
            'PLACEFP', properties->>'PLACEFP',
            'STATEFP', properties->>'STATEFP'
        ) AS city_info
    FROM (
        SELECT jsonb_array_elements((ST_AsGeoJSON(geom)::jsonb)->'features') AS feature
        FROM ogr_fdw_layer
        WHERE filename = '$GEOJSON_FILE2'
    ) AS features
    CROSS JOIN LATERAL (SELECT feature->'properties' AS properties) AS props
)
UPDATE demographics d
SET city = city || city_info
FROM cities_data c
WHERE d.state = c.statefp;
"

echo "✅ Done setting up the demographics table with states, counties, and cities!"
