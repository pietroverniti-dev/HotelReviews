from pymongo import MongoClient
from dotenv import load_dotenv
import os
import asyncio
import logging
import tornado
import json
from bson import ObjectId
from datetime import datetime

logging.basicConfig(
    level = logging.INFO,
    format='%(message)s'
)

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# ========== HOTEL_HANDLER ==========
class HotelHandler(tornado.web.RequestHandler):
    
    @property
    def db(self):
        return self.application.settings['db']
    
    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")
    
    async def get(self, id=None):
        if id == None:
            hotels = [hotel for hotel in self.db.hotels.find()]
            
            self.set_status(201)
            self.write(json.dumps({
                "success": True,
                "count": len(hotels),
                "hotels": hotels
            }, cls=JSONEncoder))
        else:
            self.set_status(201)
            self.write(json.dumps({
                "success": True,
                "hotel": self.db.hotels.find_one({"_id": ObjectId(id)})
            }, cls=JSONEncoder))

# ========== MAKE_APP ==========
def make_app(db):
    return tornado.web.Application(
        [
            (r"/hotel", HotelHandler),
            (r"/hotel/([^/]+)", HotelHandler)
        ],
        db = db,
        debug = True
    )

# ========== MAIN ==========
async def main():
    
    # Caricamento di UIds e Pws dal file .env
    load_dotenv()
    UIds = os.getenv('UIds')
    Pws = os.getenv('Pws')
    
    # Connessione a mongodb
    connection_string = f'mongodb+srv://{UIds}:{Pws}@cluster0.geflqhy.mongodb.net/?appName=Cluster0'
    client = MongoClient(connection_string)
    
    db = client['Verniti']
    
    # Creazine e partenza dell'app
    app = make_app(db)
    app.listen(8888)
    
    logging.info(f'Server started...')
    logging.info(f'Database: {db.name}')
    
    try:
        await asyncio.Event().wait()
    finally:
        client.close()
        logging.info(f'MongoDB connection closed')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('Server stopped')