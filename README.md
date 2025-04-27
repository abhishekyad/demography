# demography
run the following installation commands.

pip install pandas us census tqdm flask psycopg2 geopandas

pip install redis, gdal geopy geojson shapely

install PostgreSQL and PostGIS in your machine

The scraper.py scrapes data from us census website and combines them with corresponding shapefiles to store all demographics and boundaries as geojson files. **Note** No need to run scraper.py for geojson files are attached to this repository. If you wish to scrape, add your census api key

Now run ./database_setup.sh

This loads the geojson files inside your database. Be sure to configure the database credentials inside this file. This step will take several minutes

now inside your directory do- cd backend
                              uvicorn app:app --reload

                              This runs the app on your localhost
Now in a new tab, run pyton3 -m http.server 4000

This will trigger the frontend code. Enjoy!

**DETAILS**

Files to load into db: three files, one for each- county, state and city are loaded. see line 7-9 in database_setup.sh
Endpoints: the backend is exposed at the following endpoints: 
          1-http://localhost:8000/geojson/{layer}/{name}      where name is name of place and layer ranges among city, county, state __
          2-http://localhost:8000/demographics/trend/{layer}/{name}?field={field_of_study}  where layer ranges from county to state (trend data is not shown for city), and field of study is query parameter of which you wish to see trend, eg. population__
          3-http://localhost:8000/geojson/msas/{layer}/{name} where layer ranges from city to state __
          4-http://localhost:8000/geojson/nearby_cities/city/{name}__

**Explanation**
1-  this endpoint fetches the location/boundary of the place you search for. If a county/state is searched, a boundary with an enclosed area is shown, for a city, a point is shown.

2-  this endpoint provides the trend of queried demographic across time. A trend for the last 9 years is given.

3-  this endpoint shows the counties encompassing a state. If a city is queried, the county for that city is returned

4-  this endpoint shows upto 30 cities within a radius of 50km from the queried city. This endpoint is functional only for cities.


