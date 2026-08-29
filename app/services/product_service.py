from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.catalog.spec_sheet import build_canonical_spec_sheet
from app.repositories.product_repository import ProductRepository
from app.repositories.store_offer_repository import StoreOfferRepository
from app.schemas.product import ProductCreate


class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)
        self.offer_repository = StoreOfferRepository(db)

    def create(self, payload: ProductCreate):
        return self.repository.create(payload)

    def get(self, product_id: int):
        product = self.repository.get(product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
        product.canonical_specs = build_canonical_spec_sheet(product)
        return product

    def search(self, **filters):
        products, total = self.repository.search(**filters)
        for product in products:
            product.canonical_specs = build_canonical_spec_sheet(product)
        return products, total

    def offers(self, product_id: int):
        self.get(product_id)
        return self.offer_repository.get_for_product(product_id)

    def price_history(self, product_id: int):
        self.get(product_id)
        return self.offer_repository.get_price_history(product_id)
