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
    place_fips TEXT,
    full_name TEXT,
    population DOUBLE PRECISION,
    median_household_income DOUBLE PRECISION,
    education_total DOUBLE PRECISION,
    bachelor_degree DOUBLE PRECISION,
    masters_degree DOUBLE PRECISION,
    professional_school_degree DOUBLE PRECISION,
    doctorate_degree DOUBLE PRECISION,
    geom GEOMETRY(MultiPolygon, 4326),
    layer_type TEXT,
    region VARCHAR,
    division VARCHAR,
    statefp VARCHAR,
    statens VARCHAR,
    geoid VARCHAR,
    geoidfq VARCHAR,
    stusps VARCHAR,
    name VARCHAR,
    year DOUBLE PRECISION,
    lsad VARCHAR,
    mtfcc VARCHAR,
    funcstat VARCHAR,
    aland BIGINT,
    awater BIGINT,
    intptlat VARCHAR,
    intptlon VARCHAR,
    state_fips VARCHAR,
    name2 VARCHAR,
    means_of_transportation_to_work DOUBLE PRECISION,
    population_below_poverty_level DOUBLE PRECISION,
    countyfp VARCHAR,
    countyns VARCHAR,
    namelsad VARCHAR,
    classfp VARCHAR,
    csafp VARCHAR,
    cbsafp VARCHAR,
    metdivfp VARCHAR,
    county_fips VARCHAR,
    placefp VARCHAR,
    placens VARCHAR,
    pcicbsa VARCHAR
);
"

# 3. Load the states GeoJSON data into the demographics table
ogr2ogr -f "PostgreSQL" PG:"dbname=$DBNAME user=$USERNAME" "$GEOJSON_FILE3" -nln demographics -nlt MULTIPOLYGON -lco GEOMETRY_NAME=geom -lco FID=gid

# Update the layer_type to 'state'
psql -U "$USERNAME" -d "$DBNAME" -c "
UPDATE demographics
SET layer_type = 'state';
"

# 4. Load counties (append)
ogr2ogr -f "PostgreSQL" PG:"dbname=$DBNAME user=$USERNAME" "$GEOJSON_FILE1" -nln demographics -nlt MULTIPOLYGON -lco GEOMETRY_NAME=geom -lco FID=gid -append

# Update layer_type to 'county'
psql -U "$USERNAME" -d "$DBNAME" -c "
UPDATE demographics
SET layer_type = 'county'
WHERE layer_type IS NULL;
"

# 5. Load cities (append)
ogr2ogr -f "PostgreSQL" PG:"dbname=$DBNAME user=$USERNAME" "$GEOJSON_FILE2" -nln demographics -nlt MULTIPOLYGON -lco GEOMETRY_NAME=geom -lco FID=gid -append

# Update layer_type to 'city'
psql -U "$USERNAME" -d "$DBNAME" -c "
UPDATE demographics
SET layer_type = 'city'
WHERE layer_type IS NULL;
"

# Clear 'year' for cities
psql -U "$USERNAME" -d "$DBNAME" -c "
UPDATE demographics
SET year = NULL
WHERE layer_type = 'city';
"

# 7. Create a spatial index
psql -U "$USERNAME" -d "$DBNAME" -c "
CREATE INDEX IF NOT EXISTS idx_demographics_geom ON demographics USING GIST (geom);
"

echo "✅ Done loading and updating the GeoJSON into the database with layer_type!"
