from . import db


def get_product_info(query):
    return db.get_products(query)
