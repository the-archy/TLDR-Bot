import pymongo
from config import MONGODB_URL
from modules import cache


class Connection:
    def __init__(self):
        self.mongo_client = pymongo.MongoClient(MONGODB_URL)
        self.db = self.mongo_client['TLDR']
        self.server_options = self.db['server_options']
        self.levels = self.db['levels']

    def _get_server_options(self, guild_id):
        doc = self.server_options.find_one({'guild_id': guild_id})
        if doc is None:
            new_doc = {
                'guild_id': guild_id,
                'prefix': '>',
                'embed_colour': 0x00a6ad
            }
            self.server_options.insert_one(new_doc)
            doc = new_doc

        return doc

    @cache.cache()
    def get_server_options(self, option, guild_id):
        doc = self._get_server_options(guild_id)
        return doc[option]

    def _get_levels(self, guild_id):
        doc = self.levels.find_one({'guild_id': guild_id})
        if doc is None:
            doc = {
                'guild_id': guild_id,
                'users': {},
                'level_up_channel': 0,
                'leveling_routes': {
                    'parliamentary': [
                        ('Citizen', 5),
                        ('Local Councillor', 5)
                    ],
                    'honours': [
                        ('Public Servant', 5)
                    ]
                },
                'honours_channels': []
            }
            self.levels.insert_one(doc)
        return doc

    @cache.cache()
    def get_levels(self, value, guild_id, user_id=None):
        doc = self._get_levels(guild_id)
        if user_id is None:
            return doc[value]
        user_id = str(user_id)
        if user_id not in doc['users']:
            user = {
                'pp': 0,
                'p_level': 0,
                'hp': 0,
                'h_level': 0,
                'p_role': 'Citizen',
                'h_role': ''
            }
            self.levels.update_one({'guild_id': guild_id}, {'$set': {f'users.{user_id}': user}})
            doc['users'][user_id] = user

        return doc['users'][user_id][value]
