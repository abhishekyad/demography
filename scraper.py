import os
import pandas as pd
from tqdm import tqdm
from census import Census
from us import states
import geopandas as gpd
import time

# Set your Census API Key here
CENSUS_API_KEY = '4b6933bcc58a48470f3c87be53cf90f34de34c61'
c = Census(CENSUS_API_KEY)

# Define which fields you want to extract
FIELDS = {
    'NAME': 'name',
    'B01003_001E': 'population',
    'B19013_001E': 'median_household_income',
    'B15003_001E': 'education_total',
    'B15003_022E': 'bachelor_degree',
    'B15003_023E': 'masters_degree',
    'B08301_001E': 'means_of_transportation_to_work',
    'B17001_002E': 'population_below_poverty_level'
}

def fetch_county_data(year):
    print(f"Fetching county data for {year}...")
    counties = c.acs5.get(list(FIELDS.keys()), {'for': 'county:*'}, year=year)
    df = pd.DataFrame(counties)
    df = df.rename(columns=FIELDS)
    df['state_name'] = df['state'].apply(lambda x: states.lookup(x).name if states.lookup(x) else x)
    df['county_fips'] = df['state'] + df['county']
    df['full_name'] = df['name'] + ", " + df['state_name']
    df.loc[df['median_household_income'] < 0, 'median_household_income'] = None
    df['year'] = year  # Add year column
    df = df[['year', 'county_fips', 'full_name', 'population', 'median_household_income',
             'education_total', 'bachelor_degree', 'masters_degree',
             'means_of_transportation_to_work', 'population_below_poverty_level']]
    return df


def fetch_city_data(year):
    print(f"Fetching city/town (place) data by state for  {year}...")
    all_cities = []
    failed_states = []

    for state in states.STATES:
        try:
            print(f"Fetching places in {state.name} ({state.abbr})...")
            cities = c.acs5.get(
                list(FIELDS.keys()),
                {'for': 'place:*', 'in': f'state:{state.fips}'}
            ,year=year)
            all_cities.extend(cities)
        except Exception as e:
            print(f"Failed to fetch for {state.name}: {e}")
            failed_states.append(state)

        time.sleep(0.5)

    if failed_states:
        print("Some states failed to fetch:", [s.name for s in failed_states])

    df = pd.DataFrame(all_cities)
    df = df.rename(columns=FIELDS)
    df['state_name'] = df['state'].apply(lambda x: states.lookup(x).name if states.lookup(x) else x)
    df['place_fips'] = df['state'] + df['place']
    df['full_name'] = df['name'] + ", " + df['state_name']
    df.loc[df['median_household_income'] < 0, 'median_household_income'] = None
    df = df[['place_fips', 'full_name', 'population', 'median_household_income',
             'education_total', 'bachelor_degree', 'masters_degree', 'means_of_transportation_to_work', 'population_below_poverty_level']]
    return df


def fetch_state_data(year):
    print(f"Fetching State data for {year}...")
    states_data = c.acs5.get(list(FIELDS.keys()), {'for': 'state:*'}, year=year)
    df = pd.DataFrame(states_data)
    df = df.rename(columns=FIELDS)
    df['state_fips'] = df['state']
    df.loc[df['median_household_income'] < 0, 'median_household_income'] = None
    df['year'] = year
    df = df[['year', 'state_fips', 'name', 'population', 'median_household_income',
             'education_total', 'bachelor_degree', 'masters_degree',
             'means_of_transportation_to_work', 'population_below_poverty_level']]
    return df



# Save to CSV
def save_to_csv(df, filename):
    df.to_csv(filename, index=False)
    print(f"Saved {filename}")

def load_state_shapes(shapefile_path):
    print("Loading state shapefile...")
    gdf = gpd.read_file(shapefile_path)
    gdf['state_fips'] = gdf['STATEFP']
    return gdf

# Read county shapefile
def load_county_shapes(shapefile_path):
    print("Loading county shapefile...")
    gdf = gpd.read_file(shapefile_path)
    gdf['county_fips'] = gdf['STATEFP'] + gdf['COUNTYFP']
    return gdf

# Read city (place) shapefile
def load_city_shapes(shapefile_path):
    print("Loading city (place) shapefile...")
    gdf = gpd.read_file(shapefile_path)
    gdf['place_fips'] = gdf['STATEFP'] + gdf['PLACEFP']
    return gdf

# Merge demographic DataFrame with shape GeoDataFrame
def merge_shapes(demographics_df, shapes_gdf, key):
    print(f"Merging on {key}...")
    merged = shapes_gdf.merge(demographics_df, on=key, how='left')
    return merged


if __name__ == "__main__":
    years = range(2015, 2024)  # Fetch 2015 to 2023

    all_county_dfs = []
    all_city_dfs = []
    all_state_dfs = []

    for year in years:
        city_df = fetch_city_data(year)
        county_df = fetch_county_data(year)
        state_df = fetch_state_data(year)

        save_to_csv(county_df, f'counties_demographics_{year}.csv')
        save_to_csv(city_df, f'cities_demographics_{year}.csv')
        save_to_csv(state_df, f'states_demographics_{year}.csv')

        all_county_dfs.append(county_df)
        all_city_dfs.append(city_df)
        all_state_dfs.append(state_df)

    # Optionally, concatenate all years together
    full_county_df = pd.concat(all_county_dfs)
    full_city_df = pd.concat(all_city_dfs)
    full_state_df = pd.concat(all_state_dfs)

    save_to_csv(full_county_df, 'counties_demographics_all_years.csv')
    save_to_csv(full_city_df, 'cities_demographics_all_years.csv')
    save_to_csv(full_state_df, 'states_demographics_all_years.csv')



    # Load shapefiles
    county_shapes = load_county_shapes('./shapes/COUNTY/tl_2023_us_county/tl_2023_us_county.shp')
    state_shapes = load_state_shapes('./shapes/STATE/tl_2023_us_state/tl_2023_us_state.shp')
    df=pd.DataFrame()
    for item in os.listdir('./shapes/PLACE'):
        item_path=os.path.join('./shapes/PLACE',item)
        if os.path.isdir(item_path):
            for item_new in os.listdir(item_path):
                file=item+'.shp'
                city_shapes = load_city_shapes(os.path.join(item_path,file))
                df=pd.concat([df,city_shapes])

    # Merge demographics with shapes
    counties_geo = merge_shapes(full_county_df, county_shapes, 'county_fips')
    cities_geo = merge_shapes(full_city_df, df, 'place_fips')
    #states_geo = merge_shapes(full_state_df,state_shapes,'state_fips')

    # Save the merged GeoDataFrames
    counties_geo.to_file('counties_demographics.geojson', driver='GeoJSON')
    cities_geo.to_file('cities_demographics.geojson', driver='GeoJSON')
    states_geo.to_file('states_demographics.geojson', driver='GeoJSON')

    print("Saved merged shapefiles with demographic data!")



