import asyncio
import tornado.web
import tornado.platform.asyncio
from pymongo import AsyncMongoClient
import json
from bson import ObjectId
from datetime import datetime
import re
import logging
from dotenv import load_dotenv
import os

logging.basicConfig(
    level = logging.INFO,
    format = '%(message)s'
)

# ========== JSON Encoder ==========
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# ========== Validazione ==========
def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

def validate_phone(phone):
    return re.match(r"^\+?\d{6,15}$", phone) is not None

# ========== Funzione per normalizzare documenti ==========
def normalize(doc):
    if doc is None:
        return None
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


# =========================================================
#                      HOTEL HANDLER
# =========================================================
class HotelHandler(tornado.web.RequestHandler):

    @property
    def db(self):
        return self.application.settings['db']

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    # -----------------------------------------------------
    async def get(self, hotel_id=None):
        """GET /hotels  oppure  GET /hotels/{id}"""

        # ===========================
        # GET /hotels/{id}
        # ===========================
        if hotel_id is not None:

            # controllo ID
            if not ObjectId.is_valid(hotel_id):
                self.set_status(400)
                return self.write({"error": "ID hotel non valido"})

            # cerco hotel
            hotel = await self.db.hotels.find_one({"_id": ObjectId(hotel_id)})
            if hotel is None:
                self.set_status(404)
                return self.write({"error": "Hotel non trovato"})

            # normalizzo hotel
            hotel = normalize(hotel)

            # prendo recensioni
            cursor = self.db.reviews.find({"hotel_id": ObjectId(hotel_id)})
            reviews = [normalize(r) for r in await cursor.to_list(None)]

            hotel["reviews"] = reviews

            # rating medio
            if len(reviews) > 0:
                media = sum(r["rating"] for r in reviews) / len(reviews)
                hotel["avg_rating"] = round(media)
            else:
                hotel["avg_rating"] = None

            return self.write(hotel)

        # ===========================
        # GET /hotels con filtri
        # ===========================
        query = {}

        # filtro city
        city = self.get_query_argument("city", None)
        if city:
            query["city"] = {"$regex": city, "$options": "i"}

        # filtro name
        name = self.get_query_argument("name", None)
        if name:
            query["name"] = {"$regex": name, "$options": "i"}

        # leggo tutti gli hotel che rispettano i filtri
        hotels_cursor = self.db.hotels.find(query)
        hotels = []
        async for h in hotels_cursor:
            h = normalize(h)

            # prendo recensioni di ogni hotel
            cur = self.db.reviews.find({"hotel_id": ObjectId(h["id"])})
            reviews = [normalize(r) for r in await cur.to_list(None)]
            h["reviews"] = reviews

            # rating medio
            if len(reviews) > 0:
                media = sum(r["rating"] for r in reviews) / len(reviews)
                h["avg_rating"] = round(media)
            else:
                h["avg_rating"] = None

            hotels.append(h)

        # filtro per rating medio se richiesto
        rating = self.get_query_argument("rating", None)
        if rating:
            rating = int(rating)
            hotels = [h for h in hotels if h["avg_rating"] == rating]

        return self.write({"count": len(hotels), "hotels": hotels})

    # -----------------------------------------------------
    async def post(self):
        """POST /hotels"""

        # leggo body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except:
            self.set_status(400)
            return self.write({"error": "JSON non valido"})

        # campi obbligatori
        required = ("name", "city", "phone", "email")
        for r in required:
            if r not in data:
                self.set_status(400)
                return self.write({"error": f"Manca campo obbligatorio: {r}"})

        # email valida?
        if not validate_email(data["email"]):
            self.set_status(400)
            return self.write({"error": "Email non valida"})

        # telefono valido?
        if not validate_phone(data["phone"]):
            self.set_status(400)
            return self.write({"error": "Telefono non valido"})

        # inserisco hotel
        result = await self.db.hotels.insert_one(data)
        new_hotel = await self.db.hotels.find_one({"_id": result.inserted_id})
        new_hotel = normalize(new_hotel)

        self.set_status(201)
        return self.write(new_hotel)

    # -----------------------------------------------------
    async def put(self, hotel_id):
        """PUT /hotels/{id}"""

        # controllo id
        if not ObjectId.is_valid(hotel_id):
            self.set_status(400)
            return self.write({"error": "ID non valido"})

        # leggo body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except:
            self.set_status(400)
            return self.write({"error": "JSON non valido"})

        # validazioni
        if "email" in data:
            if not validate_email(data["email"]):
                self.set_status(400)
                return self.write({"error": "Email non valida"})

        if "phone" in data:
            if not validate_phone(data["phone"]):
                self.set_status(400)
                return self.write({"error": "Telefono non valido"})

        # aggiorno hotel
        result = await self.db.hotels.update_one(
            {"_id": ObjectId(hotel_id)},
            {"$set": data}
        )

        if result.matched_count == 0:
            self.set_status(404)
            return self.write({"error": "Hotel non trovato"})

        # eliminazione recensioni associate
        await self.db.reviews.delete_many({"hotel_id": ObjectId(hotel_id)})

        updated = await self.db.hotels.find_one({"_id": ObjectId(hotel_id)})
        updated = normalize(updated)

        return self.write(updated)

    # -----------------------------------------------------
    async def delete(self, hotel_id):
        """DELETE /hotels/{id}"""

        # controllo id
        if not ObjectId.is_valid(hotel_id):
            self.set_status(400)
            return self.write({"error": "ID non valido"})

        # elimino hotel
        await self.db.hotels.delete_one({"_id": ObjectId(hotel_id)})

        # elimino recensioni collegate
        await self.db.reviews.delete_many({"hotel_id": ObjectId(hotel_id)})

        return self.write({"message": "Hotel e recensioni eliminati"})
        

# =========================================================
#                 HOTEL REVIEWS HANDLER
# =========================================================
class HotelReviewsHandler(tornado.web.RequestHandler):

    @property
    def db(self):
        return self.application.settings['db']

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    # -----------------------------------------------------
    async def get(self, hotel_id, review_id=None):
        """GET /hotels/{id}/reviews  oppure  GET /hotels/{id}/reviews/{review_id}"""

        # controllo hotel_id
        if not ObjectId.is_valid(hotel_id):
            self.set_status(400)
            return self.write({"error": "Hotel ID non valido"})

        # -----------------------------------------
        # GET /hotels/{id}/reviews/{review_id}
        # -----------------------------------------
        if review_id is not None:
            if not ObjectId.is_valid(review_id):
                self.set_status(400)
                return self.write({"error": "Review ID non valido"})

            review = await self.db.reviews.find_one({
                "_id": ObjectId(review_id),
                "hotel_id": ObjectId(hotel_id)
            })

            if review is None:
                self.set_status(404)
                return self.write({"error": "Recensione non trovata"})

            return self.write(normalize(review))

        # -----------------------------------------
        # GET /hotels/{id}/reviews
        # -----------------------------------------
        cur = self.db.reviews.find({"hotel_id": ObjectId(hotel_id)})
        reviews = [normalize(r) for r in await cur.to_list(None)]

        return self.write({"count": len(reviews), "reviews": reviews})

    # -----------------------------------------------------
    async def post(self, hotel_id):
        """POST /hotels/{id}/reviews"""

        # controllo hotel_id
        if not ObjectId.is_valid(hotel_id):
            self.set_status(400)
            return self.write({"error": "Hotel ID non valido"})

        # controllo se hotel esiste
        hotel = await self.db.hotels.find_one({"_id": ObjectId(hotel_id)})
        if hotel is None:
            self.set_status(404)
            return self.write({"error": "Hotel non trovato"})

        # leggo body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except:
            self.set_status(400)
            return self.write({"error": "JSON non valido"})

        # campi obbligatori
        if "user" not in data:
            self.set_status(400)
            return self.write({"error": "Campo mancante: user"})

        if "rating" not in data:
            self.set_status(400)
            return self.write({"error": "Campo mancante: rating"})

        # validazioni
        if not validate_email(data["user"]):
            self.set_status(400)
            return self.write({"error": "Email non valida"})

        if not (1 <= data["rating"] <= 5):
            self.set_status(400)
            return self.write({"error": "Rating deve essere tra 1 e 5"})

        # creo recensione
        data["hotel_id"] = ObjectId(hotel_id)
        result = await self.db.reviews.insert_one(data)

        new_rev = await self.db.reviews.find_one({"_id": result.inserted_id})
        new_rev = normalize(new_rev)

        self.set_status(201)
        return self.write(new_rev)

    # -----------------------------------------------------
    async def put(self, hotel_id, review_id):
        """PUT /hotels/{id}/reviews/{review_id}"""

        # controllo ID
        if not ObjectId.is_valid(hotel_id) or not ObjectId.is_valid(review_id):
            self.set_status(400)
            return self.write({"error": "ID non valido"})

        # leggo body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except:
            self.set_status(400)
            return self.write({"error": "JSON non valido"})

        # validazioni
        if "user" in data and not validate_email(data["user"]):
            self.set_status(400)
            return self.write({"error": "Email non valida"})

        if "rating" in data and not (1 <= data["rating"] <= 5):
            self.set_status(400)
            return self.write({"error": "Rating non valido"})

        # aggiorno
        result = await self.db.reviews.update_one(
            {"_id": ObjectId(review_id), "hotel_id": ObjectId(hotel_id)},
            {"$set": data}
        )

        if result.matched_count == 0:
            self.set_status(404)
            return self.write({"error": "Recensione non trovata"})

        updated = await self.db.reviews.find_one({"_id": ObjectId(review_id)})
        updated = normalize(updated)

        return self.write(updated)

    # -----------------------------------------------------
    async def delete(self, hotel_id, review_id):
        """DELETE /hotels/{id}/reviews/{review_id}"""

        # controllo ID
        if not ObjectId.is_valid(hotel_id) or not ObjectId.is_valid(review_id):
            self.set_status(400)
            return self.write({"error": "ID non valido"})

        # elimino recensione
        result = await self.db.reviews.delete_one(
            {"_id": ObjectId(review_id), "hotel_id": ObjectId(hotel_id)}
        )

        if result.deleted_count == 0:
            self.set_status(404)
            return self.write({"error": "Recensione non trovata"})

        return self.write({"message": "Recensione eliminata"})

# ========== Make app ==========
def make_app(db):
    """Crea applicazione Tornado con riferimento al database"""
    return tornado.web.Application(
        [
            (r"/hotels", HotelHandler),
            (r"/hotels/([^/]+)", HotelHandler),
            (r"/hotels/([^/]+)/reviews", HotelReviewsHandler),
            (r"/hotels/([^/]+)/reviews/([^/]+)", HotelReviewsHandler),
        ],
        db=db,
        debug=True
    )

# ========== Main ==========
async def main():
    load_dotenv()
    UIds = os.getenv("UIds")
    Pws = os.getenv("Pws")

    connection_string = f"mongodb+srv://{UIds}:{Pws}@cluster0.geflqhy.mongodb.net/?appName=Cluster0"
    client = AsyncMongoClient(connection_string)

    db = client['Verniti']
    
    app = make_app(db)
    port = 8888
    app.listen(port)
    
    logging.info('Server started...')

    try:
        await asyncio.Event().wait()
    finally:
        client.close()
        logging.info("\nMongoDB closed")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('Server stopped!')