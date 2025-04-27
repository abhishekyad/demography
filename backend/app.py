from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import aioredis
import json
import logging
from shapely.geometry import shape

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI()

# Enable CORS
origins = ["http://localhost:4000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global database pool and Redis connection
db_pool = None
redis_client = None

# FastAPI startup and shutdown events
@app.on_event("startup")
async def startup():
    global db_pool, redis_client
    try:
        db_pool = await asyncpg.create_pool(
            database="geodata",
            user="postgres",
            password="qwerty",
            host="localhost",
            port="5432",
            min_size=1,
            max_size=10,
        )
        logger.info("Connected to PostgreSQL.")
    except Exception as e:
        logger.error(f"PostgreSQL connection error: {e}")
        raise

    try:
        redis_client = await aioredis.from_url("redis://localhost", decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis.")
    except Exception as e:
        redis_client = None
        logger.error(f"Redis connection error: {e}")

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.close()

# Helper Functions
async def safe_redis_get(key):
    if not redis_client:
        return None
    try:
        return await redis_client.get(key)
    except Exception:
        logger.warning("Redis unavailable, skipping cache get.")
        return None

async def safe_redis_set(key, value):
    if not redis_client:
        return
    try:
        await redis_client.set(key, value)
    except Exception:
        logger.warning("Redis unavailable, skipping cache set.")

def validate_layer_type(layer_type):
    valid_layers = {"cities", "counties", "states", "places", "msas"}
    if layer_type not in valid_layers:
        raise HTTPException(status_code=400, detail="Invalid layer type")

def validate_field(field):
    allowed_fields = {"population", "median_age", "median_income"}
    if field not in allowed_fields:
        raise HTTPException(status_code=400, detail="Invalid field")

# API Routes
@app.get("/geojson/{layer_type}/{name}")
async def get_geojson(layer_type: str, name: str):
    validate_layer_type(layer_type)
    key = f"{layer_type}:{name}"

    cached_data = await safe_redis_get(key)
    if cached_data:
        logger.info(f"Cache hit: {key}")
        return json.loads(cached_data)

    async with db_pool.acquire() as conn:
        try:
            result = await conn.fetchrow(f"SELECT * FROM {layer_type} WHERE name = $1", name)
            if not result:
                raise HTTPException(status_code=404, detail="Feature not found")
            data = dict(result)
            await safe_redis_set(key, json.dumps(data))
            return data
        except Exception as e:
            logger.error(f"DB error: {e}")
            raise HTTPException(status_code=500, detail="Database error")

@app.get("/geojson/nearby_cities/{layer}/{name}")
async def get_nearby_cities(layer: str, name: str, distance: float = 1.0):
    validate_layer_type(layer)
    key = f"nearby:{layer}:{name}:{distance}"

    cached_data = await safe_redis_get(key)
    if cached_data:
        logger.info(f"Cache hit: {key}")
        return json.loads(cached_data)

    async with db_pool.acquire() as conn:
        try:
            city = await conn.fetchrow(f"SELECT geometry FROM {layer} WHERE name = $1", name)
            if not city:
                raise HTTPException(status_code=404, detail="City not found")

            city_shape = shape(json.loads(city["geometry"]))
            centroid = city_shape.centroid
            lat, lon = centroid.y, centroid.x

            nearby = await conn.fetch(f"""
                SELECT *, ST_Distance(
                    ST_SetSRID(ST_Point($1, $2), 4326),
                    ST_SetSRID(ST_Point(longitude, latitude), 4326)
                ) AS distance
                FROM {layer}
                WHERE name != $3
                ORDER BY distance ASC
                LIMIT 5
            """, lon, lat, name)

            nearby_list = [dict(row) for row in nearby]
            await safe_redis_set(key, json.dumps(nearby_list))
            return nearby_list
        except Exception as e:
            logger.error(f"DB error: {e}")
            raise HTTPException(status_code=500, detail="Database error")

@app.get("/geojson/msas/{layer_type}/{name}")
async def get_msa_or_county(layer_type: str, name: str):
    return await get_geojson(layer_type, name)

@app.get("/trend/{field}")
async def get_trend(field: str):
    validate_field(field)
    key = f"trend:{field}"

    cached_data = await safe_redis_get(key)
    if cached_data:
        logger.info(f"Cache hit: {key}")
        return json.loads(cached_data)

    async with db_pool.acquire() as conn:
        try:
            trend_data = await conn.fetch(f"""
                SELECT {field}, COUNT(*) as count
                FROM cities
                GROUP BY {field}
                ORDER BY count DESC
                LIMIT 10
            """)
            trend_list = [dict(row) for row in trend_data]
            await safe_redis_set(key, json.dumps(trend_list))
            return trend_list
        except Exception as e:
            logger.error(f"DB error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
